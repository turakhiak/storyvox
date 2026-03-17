import os
import edge_tts
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TTSService:
    """
    Text-to-Speech service using edge-tts.
    Provides natural-sounding voices without requiring an API key.
    """
    
    # Default voices for different genders/ages/accents
    # edge-tts voices: https://github.com/rany2/edge-tts/blob/master/src/edge_tts/voices.json
    VOICE_MAPPING = {
        "male_us": "en-US-GuyNeural",
        "male_gb": "en-GB-ThomasNeural",
        "male_au": "en-AU-WilliamNeural",
        "female_us": "en-US-AvaNeural",
        "female_gb": "en-GB-SoniaNeural",
        "female_au": "en-AU-NatashaNeural",
        "narrator": "en-GB-RyanNeural", # Deep, authoritative
        "child_boy": "en-US-AnaNeural",
        "child_girl": "en-US-AnaNeural",
    }

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def pick_voice(self, gender: str = "narrator", age: str = "adult", personality: list = None) -> str:
        """Pick a distinctive voice based on character traits."""
        gender = (gender or "narrator").lower()
        age = (age or "adult").lower()
        personality = [p.lower() for p in (personality or [])]

        # 1. Narrator logic
        if gender == "narrator":
            return self.VOICE_MAPPING["narrator"]

        # 2. Child logic
        if age in ["child", "young", "teen"]:
            return self.VOICE_MAPPING["child_boy"] if gender == "male" else self.VOICE_MAPPING["child_girl"]

        # 3. Adult logic with variety based on personality (simplified mapping to accents)
        # We'll use personality strings to 'flavor' the accent for variety
        accents = ["us", "gb", "au"]
        # Determine accent based on first letter of name or similar hash if available? 
        # For now, let's just pick based on a simple heuristic or rotation.
        # But even better: let's use the personality hints.
        
        accent = "us"
        if any(p in ["proper", "formal", "royal", "stoic"] for p in personality):
            accent = "gb"
        elif any(p in ["rough", "wild", "friendly", "outdoorsy"] for p in personality):
            accent = "au"

        key = f"{gender}_{accent}"
        return self.VOICE_MAPPING.get(key, self.VOICE_MAPPING.get(f"{gender}_us", self.VOICE_MAPPING["narrator"]))

    async def generate_audio(
        self,
        text: str,
        filename: str,
        voice: Optional[str] = None,
        gender: Optional[str] = None,
        age: Optional[str] = None,
        personality: Optional[list] = None
    ) -> str:
        """
        Generates an MP3 file for the given text.
        Returns the absolute path to the generated file.
        Retries up to 4 times with exponential backoff — edge-tts can get
        transient 403s from Microsoft's endpoint when hit too fast.
        """
        if not voice:
            voice = self.pick_voice(gender=gender, age=age, personality=personality)

        output_path = os.path.join(self.output_dir, filename)

        max_retries = 4
        for attempt in range(max_retries):
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(output_path)
                return output_path
            except Exception as e:
                err_str = str(e)
                is_last = attempt == max_retries - 1
                # 403 / 503 from Microsoft's endpoint — retry with backoff
                if ("403" in err_str or "503" in err_str or "Invalid response" in err_str) and not is_last:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"edge-tts transient error (attempt {attempt+1}/{max_retries}), retrying in {wait}s: {e}")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Failed to generate audio with edge-tts: {e}")
                raise e

    async def list_voices(self):
        """List available voices from edge-tts."""
        return await edge_tts.VoicesManager.create()
