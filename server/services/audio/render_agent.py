import logging
import os
from typing import Any
from sqlalchemy.orm import Session
from models.database import Screenplay, ScreenplaySegment, Character
from services.tts.service import TTSService
from .sfx_service import SFXService
from config import settings

logger = logging.getLogger(__name__)

class AudioRenderAgent:
    """
    Master Audio Agent that orchestrates the production of a full radio play.
    It takes a screenplay and a sound plan, then coordinates voices, SFX, 
    and ambience to create a rich audio experience.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.audio_dir = os.path.join(settings.upload_dir, "audio")
        self.tts = TTSService(output_dir=self.audio_dir)
        self.sfx = SFXService(output_dir=self.audio_dir)

    async def render_chapter(self, screenplay_id: str, force: bool = False):
        """
        Processes an entire chapter, generating all necessary audio assets.
        Differentiates between dialogue (TTS) and sound cues (SFX).

        Authoritatively sets `screenplay.audio_status` based on outcome:
          - "complete" — every segment that needed audio produced an audio_url
          - "partial"  — some segments rendered, others failed
          - "failed"   — nothing rendered at all
        Callers should NOT override this value on success — trust what we set.

        Session safety: ORM instances are only read/written on the main task.
        The concurrent phase operates on plain-dict "render plans" and produces
        plain-dict "outcomes" — zero SQLAlchemy access inside the gather. This
        is defensive: asyncio is single-threaded so atomic attribute writes
        would technically be safe, but any future lazy-loaded relationship or
        autoflush-triggering query inside a task would silently break under
        load. Isolating the concurrent phase removes the whole class of hazard.
        """
        import asyncio

        screenplay = self.db.query(Screenplay).filter(Screenplay.id == screenplay_id).first()
        if not screenplay:
            raise ValueError(f"Screenplay {screenplay_id} not found")

        # Get character voice mapping
        characters = self.db.query(Character).filter(Character.book_id == screenplay.chapter.book_id).all()
        char_map = {c.name.lower(): c for c in characters}

        segments = (
            self.db.query(ScreenplaySegment)
            .filter(ScreenplaySegment.screenplay_id == screenplay_id)
            .order_by(ScreenplaySegment.order_index)
            .all()
        )

        logger.info(f"🎧 AUDIO RENDER AGENT: Starting render for Screenplay {screenplay_id} ({len(segments)} segments)")

        # Handle Sound Plan Ambience (Future Enhancement)
        # if screenplay.sound_plan:
        #    await self._process_sound_plan(screenplay.sound_plan, screenplay_id)

        # ──────────────────────────────────────────────────────────────────
        # Phase 1 (main task) — build plain-dict render plans from the ORM.
        # Every value we'll need inside a concurrent task is resolved here,
        # so the concurrent phase never touches SQLAlchemy.
        # ──────────────────────────────────────────────────────────────────
        render_plans: list[dict[str, Any]] = []
        for seg in segments:
            # Ephemeral-filesystem guard: on Render's free plan (no persistent disk),
            # `./uploads/audio` is wiped on every restart. A segment can have
            # `audio_url` set in the DB but point at a vanished file. Treat those as
            # missing so the render regenerates them without needing force=True.
            has_audio = False
            if seg.audio_url:
                if seg.audio_url.startswith("/static/audio/"):
                    fname = os.path.basename(seg.audio_url)
                    has_audio = os.path.exists(os.path.join(self.audio_dir, fname))
                else:
                    # Unknown URL scheme (e.g. future R2/S3) — trust the DB
                    has_audio = True

            plan: dict[str, Any] = {
                "seg_id": seg.id,
                "order_index": seg.order_index,
                "type": seg.type,
                "text": seg.text or "",
                "already_has_audio": has_audio,
                # TTS parameters — defaults for narration / sound-cue narrator fallback
                "voice": None,
                "gender": "narrator",
                "age": "adult",
                "personality": [],
            }
            if seg.type == "dialogue" and seg.character_name:
                char = char_map.get(seg.character_name.lower())
                if char:
                    plan["voice"] = char.voice_id
                    plan["gender"] = (char.gender or "narrator").lower()
                    plan["age"] = (char.age_range or "adult").lower()
                    plan["personality"] = char.personality or []
            render_plans.append(plan)

        semaphore = asyncio.Semaphore(5)  # Moderate concurrency for gTTS/Azure REST (no WebSocket limits)

        # ──────────────────────────────────────────────────────────────────
        # Phase 2 (concurrent) — render each segment. Produces plain-dict
        # outcomes only. No ORM access whatsoever.
        # ──────────────────────────────────────────────────────────────────
        async def render_segment(plan: dict[str, Any]) -> dict[str, Any]:
            if plan["already_has_audio"] and not force:
                return {"seg_id": plan["seg_id"], "status": "skipped"}

            async with semaphore:
                filename = f"{screenplay_id}_{plan['order_index']}.mp3"
                try:
                    if plan["type"] == "sound_cue":
                        # Try Freesound first — falls back to narrator TTS if no key / no match
                        sfx_path = await self.sfx.generate_sfx(
                            description=plan["text"].strip().rstrip("."),
                            filename=filename,
                        )
                        if not sfx_path:
                            # Fallback: narrator reads the sound description aloud
                            stage_text = plan["text"].strip().rstrip(".")
                            await self.tts.generate_audio(
                                text=stage_text,
                                filename=filename,
                                gender="narrator",
                                age="adult",
                                personality=["formal", "stoic"],
                            )
                        url = f"/static/audio/{filename}"

                    elif plan["type"] in ("dialogue", "narration"):
                        await self.tts.generate_audio(
                            text=plan["text"],
                            filename=filename,
                            voice=plan["voice"],
                            gender=plan["gender"],
                            age=plan["age"],
                            personality=plan["personality"],
                        )
                        url = f"/static/audio/{filename}"

                    else:
                        return {
                            "seg_id": plan["seg_id"],
                            "status": "failed",
                            "error": f"unknown segment type: {plan['type']!r}",
                        }

                    return {"seg_id": plan["seg_id"], "status": "succeeded", "url": url}

                except Exception as e:
                    return {
                        "seg_id": plan["seg_id"],
                        "status": "failed",
                        "error": f"{type(e).__name__}: {e}",
                    }

        # Each task catches its own exceptions, but return_exceptions=True is defensive
        # in case something escapes (e.g., asyncio.CancelledError). Escaped exceptions
        # are handled below.
        results = await asyncio.gather(
            *(render_segment(p) for p in render_plans),
            return_exceptions=True,
        )

        # ──────────────────────────────────────────────────────────────────
        # Phase 3 (main task) — write back audio_url to ORM instances and
        # compute the authoritative status. All SQLAlchemy work happens here.
        # ──────────────────────────────────────────────────────────────────
        seg_by_id = {s.id: s for s in segments}
        succeeded: list[str] = []
        failed: list[tuple[str, str]] = []  # (segment_id, error_message)
        skipped: list[str] = []

        for result in results:
            if isinstance(result, BaseException):
                # A task escaped its try/except — shouldn't happen, but log it so the
                # render isn't silently marked complete on an unaccounted-for failure.
                logger.error(
                    f"Render task escaped its try/except: {type(result).__name__}: {result}"
                )
                failed.append(("unknown", f"{type(result).__name__}: {result}"))
                continue

            seg_id = result["seg_id"]
            status = result["status"]

            if status == "skipped":
                skipped.append(seg_id)
            elif status == "succeeded":
                seg = seg_by_id.get(seg_id)
                if seg is None:
                    # The segment row vanished between our query and now — unusual
                    failed.append((seg_id, "segment no longer exists"))
                else:
                    seg.audio_url = result["url"]
                    succeeded.append(seg_id)
            else:  # "failed"
                error = result.get("error", "unknown error")
                logger.error(f"❌ Render Agent failed on segment {seg_id}: {error}")
                failed.append((seg_id, error))

        # Decide the authoritative audio_status based on outcomes.
        total_needed = len(segments) - len(skipped)
        if total_needed == 0:
            # Nothing actually needed rendering (all already had audio and force=False)
            new_status = "complete"
        elif len(failed) == 0:
            new_status = "complete"
        elif len(succeeded) == 0:
            new_status = "failed"
        else:
            new_status = "partial"

        screenplay.audio_status = new_status
        self.db.commit()

        if failed:
            sample = failed[:3]
            logger.warning(
                f"⚠️  Render finished with {len(failed)} failed / {len(succeeded)} ok / "
                f"{len(skipped)} skipped — status={new_status}. First failures: {sample}"
            )
        else:
            logger.info(
                f"✅ Render complete — {len(succeeded)} ok, {len(skipped)} skipped, status={new_status}"
            )

        return screenplay
