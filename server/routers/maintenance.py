"""
Maintenance API — one-shot cleanup operations.

Primarily useful after a deploy that wiped ephemeral files: the DB still
references `/static/covers/...` and `/static/audio/...` URLs for files that
no longer exist on disk. `scrub_stale_files` walks every Book and
ScreenplaySegment, checks whether the referenced file actually exists, and
nulls out the dead URLs + downgrades `screenplay.audio_status` so the UI
stops showing broken covers and dead Play buttons.

Idempotent — safe to run any time, not just after a deploy.
"""
import os
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.database import get_db, Book, Screenplay, ScreenplaySegment, Chapter
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


def _url_to_path(url: str) -> str | None:
    """Resolve a /static/... URL to an absolute filesystem path, or None if unknown."""
    if not url:
        return None
    if url.startswith("/static/audio/"):
        return os.path.join(settings.upload_dir, "audio", os.path.basename(url))
    if url.startswith("/static/covers/"):
        return os.path.join(settings.upload_dir, "covers", os.path.basename(url))
    # Any other scheme (absolute URL, R2 bucket, etc.) — don't touch it
    return None


@router.post("/scrub-stale-files")
async def scrub_stale_files(db: Session = Depends(get_db)):
    """
    Walk every Book + ScreenplaySegment, null out URLs whose files don't
    exist on disk, and downgrade screenplay.audio_status if needed.

    Returns a breakdown of what was cleaned. Run this once after a deploy
    that wiped ephemeral state; the UI will then correctly offer "Regenerate"
    buttons instead of pretending the files are still there.
    """
    covers_checked = 0
    covers_nulled = 0
    segments_checked = 0
    segments_nulled = 0
    screenplays_downgraded = 0

    # ── Covers ──────────────────────────────────────────────────────────
    books = db.query(Book).filter(Book.cover_url.isnot(None)).all()
    for book in books:
        covers_checked += 1
        path = _url_to_path(book.cover_url)
        # Only touch /static/covers/ URLs — leave external URLs alone
        if path is not None and not os.path.exists(path):
            logger.info(f"Scrub: nulling missing cover for book {book.id} ({book.title})")
            book.cover_url = None
            covers_nulled += 1

    # ── Audio segments ──────────────────────────────────────────────────
    # Group segments by screenplay so we can recompute audio_status correctly
    # at the screenplay level instead of flipping it per-segment.
    screenplays = (
        db.query(Screenplay)
        .filter(Screenplay.audio_status.in_(("complete", "partial")))
        .all()
    )

    for sp in screenplays:
        # Count segments before/after to decide if we need to downgrade
        total_with_audio = 0
        missing = 0
        for seg in sp.segments:
            if not seg.audio_url:
                continue
            segments_checked += 1
            path = _url_to_path(seg.audio_url)
            if path is None:
                # Unknown scheme — assume valid (e.g. future R2 URLs)
                total_with_audio += 1
                continue
            if os.path.exists(path):
                total_with_audio += 1
            else:
                seg.audio_url = None
                segments_nulled += 1
                missing += 1

        # Downgrade status if this screenplay lost audio
        if missing > 0:
            if total_with_audio == 0:
                # Every file gone → treat as never rendered
                sp.audio_status = "none"
            else:
                # Some files still there → partial
                sp.audio_status = "partial"
            screenplays_downgraded += 1
            logger.info(
                f"Scrub: screenplay {sp.id} — {missing} audio files missing, "
                f"{total_with_audio} intact; status → {sp.audio_status}"
            )

            # If the chapter was promoted to "audio_ready", pull it back to
            # "screenplay_ready" so the UI reflects reality.
            chapter = db.query(Chapter).filter(Chapter.id == sp.chapter_id).first()
            if chapter and chapter.status == "audio_ready":
                chapter.status = "screenplay_ready"

    db.commit()

    result = {
        "covers_checked": covers_checked,
        "covers_nulled": covers_nulled,
        "segments_checked": segments_checked,
        "segments_nulled": segments_nulled,
        "screenplays_downgraded": screenplays_downgraded,
    }
    logger.info(f"Scrub complete: {result}")
    return result
