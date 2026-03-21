"""
TTS Service — generates speech audio for screenplay segments.

Provider priority:
  1. Azure Speech REST API  — if AZURE_SPEECH_KEY is configured
                              Free tier: 500K chars/month, same neural voices as Edge TTS
  2. gTTS (Google Translate) — always available, no API key required
                              Different TLD accents give basic character differentiation
                              Works from any IP (cloud, local, etc.)
"""
import os
import asyncio
import logging
import tempfile
import httpx
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Voice mapping — same names as before, works for both Azure and gTTS
# ---------------------------------------------------------------------------

# Azure SSML voice names (neural, high quality)
AZURE_VOICES = {
    "male_us":    "en-US-GuyNeural",
    "male_gb":    "en-GB-RyanNeural",
    "male_au":    "en-AU-WilliamNeural",
    "female_us":  "en-US-AvaNeural",
    "female_gb":  "en-GB-SoniaNeural",
    "female_au":  "en-AU-NatashaNeural",
    "narrator":   "en-GB-RyanNeural",   # Deep, authoritative
    "child_boy":  "en-US-AnaNeural",
    "child_girl": "en-US-AnaNeural",
}

# gTTS accent mapping — different TLDs give slight accent variation
# https://gtts.readthedocs.io/en/latest/module.html#languages-gtts-lang
GTTS_ACCENTS = {
    "male_us":    ("en", "com"),        # American English
    "male_gb":    ("en", "co.uk"),      # British English
    "male_au":    ("en", "com.au"),     # Australian English
    "female_us":  ("en", "com"),
    "female_gb":  ("en", "co.uk"),
    "female_au":  ("en", "com.au"),
    "narrator":   ("en", "co.uk"),      # British narrator
    "child_boy":  ("en", "com"),
    "child_girl": ("en", "com"),
}


def _voice_key(gender: str, age: str, personality: list) -> str:
    """Map character traits to a voice_key like 'male_gb'."""
    gender = (gender or "narrator").lower()
    age = (age or "adult").lower()
    personality = [p.lower() for p in (personality or [])]

    if gender == "narrator":
        return "narrator"
    if age in ["child", "young", "teen"]:
        return "child_boy" if gender == "male" else "child_girl"

    accent = "us"
    if any(p in ["proper", "formal", "royal", "stoic", "british"] for p in personality):
        accent = "gb"
    elif any(p in ["rough", "wild", "friendly", "outdoorsy", "australian"] for p in personality):
        accent = "au"

    key = f"{gender}_{accent}"
    # Fallback chain
    if key not in AZURE_VOICES:
        key = f"{gender}_us"
    if key not in AZURE_VOICES:
        key = "narrator"
    return key


# ---------------------------------------------------------------------------
# Azure Speech REST API
# ---------------------------------------------------------------------------

async def _azure_tts(text: str, output_path: str, voice: str) -> None:
    """
    Generate audio via Azure Speech REST API.
    Requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION env vars.
    Free tier: 500,000 characters/month (F0 resource, no credit card needed).
    """
    key = getattr(settings, "azure_speech_key", None)
    region = getattr(settings, "azure_speech_region", "eastus")
    if not key:
        raise RuntimeError("AZURE_SPEECH_KEY not configured")

    ssml = (
        f"<speak version='1.0' xml:lang='en-US'>"
        f"<voice name='{voice}'>{_escape_xml(text)}</voice>"
        f"</speak>"
    )
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "User-Agent": "StoryVox/1.0",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, content=ssml.encode("utf-8"), headers=headers)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)


def _escape_xml(text: str) -> str:
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


# ---------------------------------------------------------------------------
# gTTS fallback (Google Translate TTS — no API key, works from cloud)
# ---------------------------------------------------------------------------

async def _gtts_tts(text: str, output_path: str, voice_key: str) -> None:
    """
    Generate audio via gTTS (Google Translate TTS).
    No API key needed. Works from cloud servers. Different TLD accents provide
    basic character differentiation (US, British, Australian).
    """
    from gtts import gTTS
    lang, tld = GTTS_ACCENTS.get(voice_key, ("en", "com"))
    loop = asyncio.get_running_loop()

    def _sync_generate():
        tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
        tts.save(output_path)

    await loop.run_in_executor(None, _sync_generate)


# ---------------------------------------------------------------------------
# Main TTSService
# ---------------------------------------------------------------------------

class TTSService:
    """
    Text-to-Speech service.
    Uses Azure Speech if configured, falls back to gTTS automatically.
    """

    VOICE_MAPPING = AZURE_VOICES  # Keep backward-compat attribute

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self._azure_available = bool(getattr(settings, "azure_speech_key", None))
        provider = "Azure Speech" if self._azure_available else "gTTS (Google Translate)"
        logger.info(f"TTSService initialized — provider: {provider}")
        os.makedirs(self.output_dir, exist_ok=True)

    def pick_voice(self, gender: str = "narrator", age: str = "adult",
                   personality: list = None) -> str:
        """Return an Azure voice name based on character traits."""
        key = _voice_key(gender, age, personality)
        return AZURE_VOICES[key]

    async def generate_audio(
        self,
        text: str,
        filename: str,
        voice: Optional[str] = None,         # Azure voice name override
        gender: Optional[str] = None,
        age: Optional[str] = None,
        personality: Optional[list] = None,
    ) -> str:
        """
        Generate MP3 for the given text.
        Returns absolute path to the generated file.
        """
        if not text or not text.strip():
            raise ValueError("Cannot generate audio for empty text")

        output_path = os.path.join(self.output_dir, filename)
        vkey = _voice_key(gender or "narrator", age or "adult", personality or [])
        azure_voice = voice or AZURE_VOICES[vkey]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if self._azure_available:
                    await _azure_tts(text, output_path, azure_voice)
                else:
                    await _gtts_tts(text, output_path, vkey)
                logger.debug(f"TTS OK: {filename} ({'Azure' if self._azure_available else 'gTTS'})")
                return output_path

            except Exception as e:
                err_str = str(e)
                is_last = attempt == max_retries - 1

                # Transient HTTP errors — retry
                if not is_last and any(
                    kw in err_str for kw in ("429", "503", "502", "timeout", "Timeout")
                ):
                    wait = 2 ** attempt
                    logger.warning(f"TTS transient error, retrying in {wait}s: {e}")
                    await asyncio.sleep(wait)
                    continue

                # Azure failed — try gTTS as emergency fallback
                if self._azure_available and not is_last:
                    logger.warning(f"Azure TTS failed, falling back to gTTS: {e}")
                    try:
                        await _gtts_tts(text, output_path, vkey)
                        return output_path
                    except Exception as gtts_err:
                        logger.error(f"gTTS fallback also failed: {gtts_err}")

                logger.error(f"TTS failed after {attempt + 1} attempt(s): {e}")
                raise

        raise RuntimeError(f"TTS failed after {max_retries} attempts")

    async def list_voices(self):
        """Return list of available Azure voice names."""
        return list(AZURE_VOICES.values())
