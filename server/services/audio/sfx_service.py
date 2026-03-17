import os
import re
import shutil
import logging
import httpx
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"


def _safe_cache_name(description: str) -> str:
    """Turn a sound description into a safe filename, e.g. 'door creaking' → 'door_creaking'."""
    cleaned = re.sub(r"[^\w\s-]", "", description.lower())
    cleaned = re.sub(r"[\s]+", "_", cleaned.strip())
    return cleaned[:60]  # cap length


class SFXService:
    """
    Service for generating / retrieving sound effects.

    If FREESOUND_API_KEY is set in .env, uses Freesound.org to search for and
    download a real matching sound effect (MP3 preview, ~1-15 s).  Results are
    cached on disk so the same description is only downloaded once.

    Returns None (caller falls back to TTS narrator) when:
      - No API key is configured
      - Freesound returns no results for the query
      - Any network / download error occurs
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.sfx_cache_dir = os.path.join(output_dir, "sfx_cache")
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.sfx_cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_sfx(
        self,
        description: str,
        filename: str,
        duration_ms: Optional[int] = None,
        intensity: str = "medium",
    ) -> Optional[str]:
        """
        Returns the path to an MP3 file for the given sound description,
        or None if no sound could be found / downloaded.
        """
        if not settings.freesound_api_key:
            logger.debug("No FREESOUND_API_KEY — SFX skipped")
            return None

        cache_key   = _safe_cache_name(description)
        cache_path  = os.path.join(self.sfx_cache_dir, f"{cache_key}.mp3")
        output_path = os.path.join(self.output_dir, filename)

        # --- Serve from disk cache if already downloaded ---
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1024:
            logger.info(f"🔊 SFX cache hit: '{description}'")
            shutil.copy2(cache_path, output_path)
            return output_path

        # --- Search Freesound for best match ---
        try:
            preview_url = await self._search_freesound(description)
            if not preview_url:
                logger.info(f"🔇 No Freesound result for: '{description}'")
                return None

            # --- Download the preview MP3 ---
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(preview_url)
                resp.raise_for_status()
                audio_bytes = resp.content

            if len(audio_bytes) < 1024:
                logger.warning(f"SFX download too small for '{description}', skipping")
                return None

            # Save to cache and output path
            with open(cache_path, "wb") as f:
                f.write(audio_bytes)
            shutil.copy2(cache_path, output_path)

            logger.info(f"🔊 SFX downloaded: '{description}' → {filename} ({len(audio_bytes)//1024} KB)")
            return output_path

        except Exception as e:
            logger.warning(f"SFX fetch failed for '{description}': {e}")
            return None

    async def generate_ambience(self, mood: str, setting: str, filename: str) -> Optional[str]:
        """Generates background ambient sound for a scene."""
        description = f"{mood} {setting} ambient background"
        return await self.generate_sfx(description, filename, intensity="low")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _search_freesound(self, description: str) -> Optional[str]:
        """
        Searches Freesound for the description and returns the HQ MP3 preview
        URL of the best match, or None.
        """
        params = {
            "query":     description,
            "token":     settings.freesound_api_key,
            "fields":    "id,name,previews,duration",
            "page_size": 5,
            "filter":    "duration:[1 TO 15]",  # Keep clips short (1–15 s)
            "sort":      "score",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(FREESOUND_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            if not results:
                return None

            # Pick the first (most relevant) result
            sound    = results[0]
            previews = sound.get("previews", {})
            url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
            return url

        except Exception as e:
            logger.warning(f"Freesound search error: {e}")
            return None
