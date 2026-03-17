"""
Batch Processing API — generate screenplay + audio for the next N chapters at a time.

Key design:
- Only processes chapters that don't already have a completed screenplay
- Saves progress per-chapter so partial batches are resumable
- If a provider fails mid-batch, completed chapters are preserved
- Tracks batch_status and batch_progress on the Book record
"""
import json
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from models.database import (
    get_db, Book, Chapter, Character, Screenplay, ScreenplaySegment,
    RevisionRound as RevisionRoundModel
)
from models.schemas import BookResponse
from services.llm.gemini_client import get_llm_client
from services.llm.pipeline import ScreenplayPipeline
from services.audio.processor import AudioProcessor
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/books/{book_id}/batch", tags=["batch"])


async def background_batch_process(
    book_id: str,
    chapter_ids: list[str],
    mode: str,
    generate_audio: bool,
    db_factory,
):
    """
    Background task: generate screenplay (and optionally audio) for a list of chapters.

    Processes one chapter at a time. If a chapter fails, it's marked as failed but
    the batch continues with the remaining chapters. Progress is saved after each chapter.
    """
    db = next(db_factory())
    completed = []
    failed = []

    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            logger.error(f"Batch: Book {book_id} not found")
            return

        # Get character bible once for all chapters
        characters = db.query(Character).filter(Character.book_id == book_id).all()
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

        # Build LLM clients once (shared circuit breakers across the batch)
        writer = get_llm_client(role="writer")
        director = get_llm_client(role="director")
        pipeline = ScreenplayPipeline(writer=writer, director=director)

        for idx, chapter_id in enumerate(chapter_ids):
            # Check if user requested a pause
            db.refresh(book)
            if book.batch_status == "paused":
                logger.info(f"Batch paused by user at chapter index {idx}")
                break

            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                failed.append(chapter_id)
                continue

            # Update batch progress
            book.batch_progress = {
                "current_chapter": chapter.number,
                "current_index": idx + 1,
                "total_in_batch": len(chapter_ids),
                "completed": completed,
                "failed": failed,
            }
            db.commit()

            logger.info(f"Batch [{idx+1}/{len(chapter_ids)}]: Chapter {chapter.number} ({chapter.title or 'untitled'})")

            # Check if screenplay already exists and is complete
            existing = (
                db.query(Screenplay)
                .filter(Screenplay.chapter_id == chapter_id, Screenplay.mode == mode)
                .first()
            )
            if existing and existing.status == "complete":
                logger.info(f"  Chapter {chapter.number} already has a complete screenplay, skipping")
                completed.append(chapter_id)
                continue

            # Remove any failed/processing screenplay
            if existing:
                db.delete(existing)
                db.flush()

            # Create new screenplay record
            screenplay = Screenplay(
                chapter_id=chapter_id,
                mode=mode,
                status="processing",
            )
            db.add(screenplay)
            db.commit()
            db.refresh(screenplay)

            try:
                # Run the pipeline
                result = await pipeline.process_chapter(
                    chapter_text=chapter.raw_text,
                    character_bible=character_bible,
                    mode=mode,
                )

                # Save revision rounds
                for rnd in result.rounds:
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

                screenplay.status = "complete"
                screenplay.total_rounds = result.total_rounds
                screenplay.final_scores = result.final_scores
                screenplay.weighted_avg = result.final_weighted_avg
                screenplay.sound_plan = result.sound_plan
                chapter.status = "screenplay_ready"
                db.commit()

                logger.info(f"  Chapter {chapter.number}: screenplay complete (score {result.final_weighted_avg:.2f})")

                # Generate audio if requested
                if generate_audio:
                    try:
                        screenplay.audio_status = "processing"
                        db.commit()
                        processor = AudioProcessor(db)
                        await processor.generate_screenplay_audio(screenplay.id, force=False)
                        screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay.id).first()
                        screenplay.audio_status = "complete"
                        chapter.status = "audio_ready"
                        db.commit()
                        logger.info(f"  Chapter {chapter.number}: audio complete")
                    except Exception as audio_err:
                        logger.error(f"  Chapter {chapter.number}: audio failed: {audio_err}")
                        screenplay.audio_status = "failed"
                        db.commit()

                completed.append(chapter_id)

            except Exception as e:
                logger.error(f"  Chapter {chapter.number} failed: {e}")
                try:
                    db.rollback()
                    screenplay = db.query(Screenplay).filter(Screenplay.id == screenplay.id).first()
                    if screenplay:
                        screenplay.status = "failed"
                        db.commit()
                except Exception:
                    pass
                failed.append(chapter_id)

                # Brief pause before next chapter to let rate limits cool
                await asyncio.sleep(5)

        # Update final batch status
        book = db.query(Book).filter(Book.id == book_id).first()
        book.batch_status = "idle"
        book.batch_progress = {
            "current_chapter": None,
            "current_index": len(chapter_ids),
            "total_in_batch": len(chapter_ids),
            "completed": completed,
            "failed": failed,
        }
        db.commit()

        logger.info(
            f"Batch complete for book {book_id}: "
            f"{len(completed)} succeeded, {len(failed)} failed"
        )

    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        try:
            book = db.query(Book).filter(Book.id == book_id).first()
            if book:
                book.batch_status = "failed"
                book.batch_progress = {
                    "completed": completed,
                    "failed": failed,
                    "error": str(e)[:200],
                }
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/generate", response_model=BookResponse, status_code=202)
async def batch_generate(
    book_id: str,
    background_tasks: BackgroundTasks,
    mode: str = Query("radio_play", regex="^(faithful|radio_play)$"),
    count: int = Query(None, description="Number of chapters to process (default: batch_size from config)"),
    start_from: int = Query(None, description="Chapter number to start from (default: bookmark + 1)"),
    audio: bool = Query(True, description="Also generate audio for each chapter"),
    db: Session = Depends(get_db),
):
    """
    Generate screenplay (and optionally audio) for the next batch of chapters.

    Picks up from the user's listening bookmark by default.
    Only processes chapters that don't already have a completed screenplay.
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    if book.batch_status == "processing":
        raise HTTPException(409, "A batch is already processing for this book. Wait for it to finish.")

    batch_size = count or settings.batch_size
    start_chapter = start_from if start_from is not None else (book.listen_bookmark or 0) + 1

    # Get candidate chapters, filter out non-story content (front/back matter)
    from services.chapter_filter import filter_story_chapters

    all_candidates = (
        db.query(Chapter)
        .filter(
            Chapter.book_id == book_id,
            Chapter.number >= start_chapter,
        )
        .order_by(Chapter.number)
        .all()
    )

    # Filter out acknowledgements, about the author, excerpts, etc.
    story_candidates = filter_story_chapters(all_candidates, book.total_chapters)

    # Take only batch_size chapters
    chapters = story_candidates[:batch_size]

    if not chapters:
        raise HTTPException(404, f"No story chapters found starting from chapter {start_chapter}")

    # Filter out chapters that already have complete screenplays
    chapter_ids_to_process = []
    for ch in chapters:
        existing = (
            db.query(Screenplay)
            .filter(Screenplay.chapter_id == ch.id, Screenplay.mode == mode)
            .first()
        )
        if not existing or existing.status != "complete":
            chapter_ids_to_process.append(ch.id)
        else:
            # Already done — still include in the "batch" view but won't re-process
            chapter_ids_to_process.append(ch.id)

    # Update book status
    book.batch_status = "processing"
    book.batch_progress = {
        "current_chapter": chapters[0].number,
        "current_index": 0,
        "total_in_batch": len(chapter_ids_to_process),
        "completed": [],
        "failed": [],
        "chapter_numbers": [ch.number for ch in chapters],
    }
    db.commit()
    db.refresh(book)

    # Trigger background batch
    background_tasks.add_task(
        background_batch_process,
        book_id,
        chapter_ids_to_process,
        mode,
        audio,
        get_db,
    )

    return book


@router.get("/status")
async def batch_status(
    book_id: str,
    db: Session = Depends(get_db),
):
    """Get the current batch processing status for a book."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    # Get chapter statuses for context
    chapters = (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id)
        .order_by(Chapter.number)
        .all()
    )

    from services.chapter_filter import is_non_story_chapter

    chapter_statuses = []
    for ch in chapters:
        screenplay = (
            db.query(Screenplay)
            .filter(Screenplay.chapter_id == ch.id)
            .first()
        )
        chapter_statuses.append({
            "number": ch.number,
            "title": ch.title,
            "chapter_id": ch.id,
            "status": ch.status,
            "screenplay_status": screenplay.status if screenplay else None,
            "audio_status": screenplay.audio_status if screenplay else None,
            "score": screenplay.weighted_avg if screenplay else None,
            "is_non_story": is_non_story_chapter(ch, book.total_chapters),
        })

    return {
        "book_id": book_id,
        "listen_bookmark": book.listen_bookmark or 0,
        "batch_status": book.batch_status or "idle",
        "batch_progress": book.batch_progress,
        "total_chapters": book.total_chapters,
        "chapters": chapter_statuses,
    }


@router.post("/stop")
async def stop_batch(
    book_id: str,
    db: Session = Depends(get_db),
):
    """
    Request a batch to stop after the current chapter finishes.
    (The background task checks batch_status each iteration.)
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    if book.batch_status != "processing":
        raise HTTPException(400, "No batch is currently processing")

    book.batch_status = "paused"
    db.commit()
    return {"status": "stopping", "message": "Batch will stop after current chapter completes"}
