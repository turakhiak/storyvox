import logging
import os
from typing import List, Dict, Any
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

        semaphore = asyncio.Semaphore(5)  # Moderate concurrency for gTTS/Azure REST (no WebSocket limits)

        async def render_segment(seg: ScreenplaySegment):
            if seg.audio_url and not force:
                return

            async with semaphore:
                filename = f"{screenplay_id}_{seg.order_index}.mp3"
                
                try:
                    if seg.type == "sound_cue":
                        # Try Freesound first — falls back to narrator TTS if no key / no match
                        sfx_path = await self.sfx.generate_sfx(
                            description=seg.text.strip().rstrip("."),
                            filename=filename,
                        )
                        if sfx_path:
                            seg.audio_url = f"/static/audio/{filename}"
                        else:
                            # Fallback: narrator reads the sound description aloud
                            stage_text = seg.text.strip().rstrip(".")
                            await self.tts.generate_audio(
                                text=stage_text,
                                filename=filename,
                                gender="narrator",
                                age="adult",
                                personality=["formal", "stoic"],
                            )
                            seg.audio_url = f"/static/audio/{filename}"

                    elif seg.type in ["dialogue", "narration"]:
                        # ROUTE TO TTS SERVICE
                        voice = None
                        gender = "narrator"
                        age = "adult"
                        personality = []
                        
                        if seg.type == "dialogue" and seg.character_name:
                            char = char_map.get(seg.character_name.lower())
                            if char:
                                voice = char.voice_id
                                gender = char.gender.lower() if char.gender else "narrator"
                                age = char.age_range.lower() if char.age_range else "adult"
                                personality = char.personality or []
                        
                        await self.tts.generate_audio(
                            text=seg.text,
                            filename=filename,
                            voice=voice,
                            gender=gender,
                            age=age,
                            personality=personality
                        )
                        seg.audio_url = f"/static/audio/{filename}"
                        
                except Exception as e:
                    logger.error(f"❌ Render Agent failed on segment {seg.id}: {e}")

        # Run all renders in parallel
        await asyncio.gather(*(render_segment(seg) for seg in segments))

        screenplay.status = "audio_ready"
        self.db.commit()
        logger.info(f"✅ AUDIO RENDER AGENT: Render complete for Screenplay {screenplay_id}")
        return screenplay
