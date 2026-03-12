"""
Screenplay API — trigger Writer/Director pipeline, get results.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models.database import (
    get_db, Chapter, Character, Screenplay, ScreenplaySegment,
    RevisionRound as RevisionRoundModel
)
from models.schemas import ScreenplayResponse, RevisionRoundResponse
from services.llm.gemini_client import GeminiClient
from services.llm.pipeline import ScreenplayPipeline
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chapters/{chapter_id}/screenplay", tags=["screenplay"])


@router.post("", response_model=ScreenplayResponse)
async def generate_screenplay(
    chapter_id: str,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    db: Session = Depends(get_db),
):
    """Generate a screenplay for a chapter using the Writer/Director pipeline."""
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
        raise HTTPException(409, "Screenplay already exists. Delete it first to regenerate.")

    # If there's a failed/processing one, delete it
    if existing:
        db.delete(existing)
        db.flush()

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

    # Create screenplay record
    screenplay = Screenplay(
        chapter_id=chapter_id,
        mode=mode,
        status="processing",
    )
    db.add(screenplay)
    db.flush()

    # Run the Writer/Director pipeline
    try:
        # Both Writer and Director use Gemini for now (free tier)
        # In production, Writer could use a cheaper/faster model
        writer = GeminiClient()
        director = GeminiClient()
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

        # Update chapter status
        chapter.status = "screenplay_ready"

        db.commit()
        db.refresh(screenplay)

        return screenplay

    except Exception as e:
        logger.error(f"Screenplay generation failed: {e}")
        screenplay.status = "failed"
        db.commit()
        raise HTTPException(500, f"Screenplay generation failed: {str(e)}")


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
