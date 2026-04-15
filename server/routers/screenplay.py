"""
Screenplay API — trigger Writer/Director pipeline, get results.
"""
import json
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from models.database import (
    get_db, Chapter, Character, Screenplay, ScreenplaySegment,
    RevisionRound as RevisionRoundModel
)
from models.schemas import ScreenplayResponse, RevisionRoundResponse
from services.llm.gemini_client import get_llm_client
from services.llm.pipeline import ScreenplayPipeline
from services.audio.processor import AudioProcessor
from config import settings
from typing import Union, Optional, Any

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chapters/{chapter_id}/screenplay", tags=["screenplay"])


async def background_generate_screenplay(
    chapter_id: str,
    mode: str,
    screenplay_id: str,
    db_factory: Any,
):
    """Background task to run the Writer/Director pipeline."""
    db = next(db_factory())
    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
        if not chapter or not screenplay:
            logger.error("Background task failed: Chapter or Screenplay not found")
            return

        # Get character bible
        characters = (
            db.query(Character)
            .filter(Character.book_id == chapter.book_id)
            .all()
        )
        character_bible = [
            {
                "name": c.name,
                "gender": c.gender,
                "age_range": c.age_range,
                "personality": c.personality,
                "speech_patterns": c.speech_patterns,
                "frequency": c.frequency,
            }
            for c in characters
        ]

        # Run the Writer/Director pipeline
        writer = get_llm_client(role="writer")
        director = get_llm_client(role="director")
        pipeline = ScreenplayPipeline(writer=writer, director=director)

        result = await pipeline.process_chapter(
            chapter_text=chapter.raw_text,
            character_bible=character_bible,
            mode=mode,
        )

        # Save revision rounds
        for i, rnd in enumerate(result.rounds):
            is_best = (rnd.round_number == result.best_round)
            revision = RevisionRoundModel(
                screenplay_id=screenplay.id,
                round_number=rnd.round_number,
                draft=rnd.screenplay,
                critique=rnd.critique,
                scores=rnd.scores,
                weighted_avg=rnd.weighted_avg,
                approved=rnd.approved,
                is_best=is_best,
            )
            db.add(revision)

        # Save final segments
        for i, seg in enumerate(result.final_screenplay):
            segment = ScreenplaySegment(
                screenplay_id=screenplay.id,
                order_index=i,
                type=seg.get("type", "narration"),
                character_name=seg.get("character"),
                text=seg.get("text", ""),
                emotion=seg.get("emotion", "neutral"),
            )
            db.add(segment)

        # Update screenplay record
        screenplay.status = "complete"
        screenplay.total_rounds = result.total_rounds
        screenplay.final_scores = result.final_scores
        screenplay.weighted_avg = result.final_weighted_avg
        screenplay.sound_plan = result.sound_plan

        # Update chapter status
        chapter.status = "screenplay_ready"

        db.commit()
        logger.info(f"Background screenplay generation complete for {chapter_id}")

    except Exception as e:
        logger.error(f"Background screenplay generation failed: {e}")
        try:
            db.rollback()
            screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
            if screenplay:
                screenplay.status = "failed"
                db.commit()
        except Exception as db_e:
            logger.error(f"Failed to update failed status in DB: {db_e}")
    finally:
        db.close()


async def background_generate_audio(
    screenplay_id: str,
    force: bool,
    db_factory: Any,
):
    """Background task to generate audio for a screenplay."""
    db = next(db_factory())
    try:
        screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
        if not screenplay:
            logger.error("Background task failed: Screenplay not found")
            return

        screenplay.audio_status = "processing"
        db.commit()

        processor = AudioProcessor(db)
        # render_chapter sets screenplay.audio_status authoritatively
        # to "complete" / "partial" / "failed" based on per-segment outcomes.
        await processor.generate_screenplay_audio(screenplay_id, force=force)

        # Reload to read the status render_chapter wrote.
        screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
        # Promote chapter.status only when every segment rendered cleanly.
        if screenplay and screenplay.audio_status == "complete":
            chapter = db.query(Chapter).filter(Chapter.id == screenplay.chapter_id).first()
            if chapter:
                chapter.status = "audio_ready"
                db.commit()
        logger.info(
            f"Background audio generation finished for screenplay {screenplay_id} "
            f"— status={screenplay.audio_status if screenplay else 'unknown'}"
        )
    except Exception as e:
        logger.error(f"Background audio generation failed: {e}")
        try:
            screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
            if screenplay:
                screenplay.audio_status = "failed"
                db.commit()
        except Exception as db_e:
            logger.error(f"Failed to handle audio failure in DB: {db_e}")
    finally:
        db.close()


@router.post("", response_model=ScreenplayResponse, status_code=202)
async def generate_screenplay(
    chapter_id: str,
    background_tasks: BackgroundTasks,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    db: Session = Depends(get_db),
):
    """Generate a screenplay for a chapter (Async)."""
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    # Check if screenplay already exists for this mode
    existing = (
        db.query(Screenplay)
        .filter(Screenplay.chapter_id == chapter_id, Screenplay.mode == mode)
        .first()
    )
    if existing and existing.status == "complete":
        raise HTTPException(409, "Screenplay already exists.")

    # If there's a failed/processing one, delete it
    if existing:
        db.delete(existing)
        db.flush()

    # Create screenplay record in 'processing' status
    screenplay = Screenplay(
        chapter_id=chapter_id,
        mode=mode,
        status="processing",
    )
    db.add(screenplay)
    db.commit()
    db.refresh(screenplay)

    # Trigger background task
    background_tasks.add_task(
        background_generate_screenplay,
        chapter_id,
        mode,
        screenplay.id,
        get_db
    )

    return screenplay


def _detect_stale_audio(screenplay: Screenplay, db: Session) -> None:
    """
    Render's free plan has no persistent disk — after a restart, all files under
    `./uploads/audio` are gone, but the DB still thinks audio is "complete".
    Before serving the screenplay to the frontend, sample a few segments and if
    their audio files no longer exist on disk, downgrade `audio_status` to
    "none" and null out the stale `audio_url`s. That way the UI shows the
    "Generate Audio" button instead of Play buttons that 404.

    Sampling (not exhaustive) keeps this cheap on hot GET requests. If the
    sample is gone, the whole batch is almost certainly gone too — and the
    user can regenerate with one click. If only some files are missing
    (extremely rare), the next render run will catch them via render_agent's
    file-existence check.
    """
    if screenplay.audio_status not in ("complete", "partial"):
        return

    audio_dir = os.path.join(settings.upload_dir, "audio")
    segments_with_audio = [s for s in screenplay.segments if s.audio_url]
    if not segments_with_audio:
        return

    # Check first + last + middle — cheap spot-check that catches a wiped disk
    sample_idxs = {0, len(segments_with_audio) // 2, len(segments_with_audio) - 1}
    missing = 0
    for i in sample_idxs:
        seg = segments_with_audio[i]
        if seg.audio_url.startswith("/static/audio/"):
            fname = os.path.basename(seg.audio_url)
            if not os.path.exists(os.path.join(audio_dir, fname)):
                missing += 1

    if missing == len(sample_idxs):
        # Every sampled file is gone — treat as a full wipe and clear all URLs
        logger.warning(
            f"Screenplay {screenplay.id}: audio files missing on disk "
            f"(ephemeral wipe?) — downgrading audio_status to 'none'"
        )
        for seg in screenplay.segments:
            if seg.audio_url and seg.audio_url.startswith("/static/audio/"):
                seg.audio_url = None
        screenplay.audio_status = "none"
        db.commit()


@router.get("", response_model=ScreenplayResponse)
async def get_screenplay(
    chapter_id: str,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    db: Session = Depends(get_db),
):
    """Get the screenplay for a chapter."""
    screenplay = (
        db.query(Screenplay)
        .filter(Screenplay.chapter_id == chapter_id, Screenplay.mode == mode)
        .first()
    )
    if not screenplay:
        raise HTTPException(404, "Screenplay not found. Generate it first.")
    _detect_stale_audio(screenplay, db)
    return screenplay


@router.get("/revisions", response_model=list[RevisionRoundResponse])
async def get_revisions(
    chapter_id: str,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    db: Session = Depends(get_db),
):
    """Get all revision rounds for a screenplay."""
    screenplay = (
        db.query(Screenplay)
        .filter(Screenplay.chapter_id == chapter_id, Screenplay.mode == mode)
        .first()
    )
    if not screenplay:
        raise HTTPException(404, "Screenplay not found")

    rounds = (
        db.query(RevisionRoundModel)
        .filter(RevisionRoundModel.screenplay_id == screenplay.id)
        .order_by(RevisionRoundModel.round_number)
        .all()
    )
    return rounds


@router.post("/audio", response_model=ScreenplayResponse, status_code=202)
async def generate_audio(
    chapter_id: str,
    background_tasks: BackgroundTasks,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Generate audio for a screenplay (Async)."""
    screenplay = (
        db.query(Screenplay)
        .filter(Screenplay.chapter_id == chapter_id, Screenplay.mode == mode)
        .first()
    )
    if not screenplay:
        raise HTTPException(404, "Screenplay not found. Generate it first.")

    # Trigger background task
    background_tasks.add_task(
        background_generate_audio,
        screenplay.id,
        force,
        get_db
    )

    return screenplay


@router.delete("")
async def delete_screenplay(
    chapter_id: str,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    db: Session = Depends(get_db),
):
    """Delete a screenplay to allow regeneration."""
    screenplay = (
        db.query(Screenplay)
        .filter(Screenplay.chapter_id == chapter_id, Screenplay.mode == mode)
        .first()
    )
    if not screenplay:
        raise HTTPException(404, "Screenplay not found")

    db.delete(screenplay)
    db.commit()
    return {"status": "deleted"}
