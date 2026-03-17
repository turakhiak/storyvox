import os
import uuid
import logging
from sqlalchemy.orm import Session
from models.database import Screenplay, ScreenplaySegment, Character
from services.tts.service import TTSService
from config import settings

logger = logging.getLogger(__name__)

from .render_agent import AudioRenderAgent

class AudioProcessor:
    def __init__(self, db: Session):
        self.db = db
        self.render_agent = AudioRenderAgent(db)

    async def generate_screenplay_audio(self, screenplay_id: str, force: bool = False):
        """
        Delegates audio production to the specialized AudioRenderAgent.
        """
        return await self.render_agent.render_chapter(screenplay_id, force=force)
