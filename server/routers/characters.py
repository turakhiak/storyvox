import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Book, Chapter, Character
from models.schemas import CharacterResponse
from services.llm.gemini_client import GeminiClient, get_llm_client
from services.llm.prompts import CHARACTER_DETECTION_PROMPT
from config import settings


# ---------------------------------------------------------------------------
# Available edge-tts voices — curated list shown in the UI
# ---------------------------------------------------------------------------
AVAILABLE_VOICES = [
    # Male voices
    {"id": "en-GB-RyanNeural",       "label": "Ryan",        "gender": "male",   "accent": "British",    "description": "Deep, authoritative — great for narrator"},
    {"id": "en-GB-ThomasNeural",     "label": "Thomas",      "gender": "male",   "accent": "British",    "description": "Refined, distinguished"},
    {"id": "en-US-GuyNeural",        "label": "Guy",         "gender": "male",   "accent": "American",   "description": "Deep, trustworthy"},
    {"id": "en-US-ChristopherNeural","label": "Christopher", "gender": "male",   "accent": "American",   "description": "Warm, conversational"},
    {"id": "en-US-EricNeural",       "label": "Eric",        "gender": "male",   "accent": "American",   "description": "Energetic, expressive"},
    {"id": "en-AU-WilliamNeural",    "label": "William",     "gender": "male",   "accent": "Australian", "description": "Friendly, casual"},
    {"id": "en-IE-ConnorNeural",     "label": "Connor",      "gender": "male",   "accent": "Irish",      "description": "Charming, lilting"},
    # Female voices
    {"id": "en-GB-SoniaNeural",      "label": "Sonia",       "gender": "female", "accent": "British",    "description": "Elegant, precise"},
    {"id": "en-GB-LibbyNeural",      "label": "Libby",       "gender": "female", "accent": "British",    "description": "Natural, warm"},
    {"id": "en-US-AvaNeural",        "label": "Ava",         "gender": "female", "accent": "American",   "description": "Confident, clear"},
    {"id": "en-US-JennyNeural",      "label": "Jenny",       "gender": "female", "accent": "American",   "description": "Friendly, approachable"},
    {"id": "en-US-AriaNeural",       "label": "Aria",        "gender": "female", "accent": "American",   "description": "Expressive, emotive"},
    {"id": "en-AU-NatashaNeural",    "label": "Natasha",     "gender": "female", "accent": "Australian", "description": "Clear, bright"},
    {"id": "en-IE-EmilyNeural",      "label": "Emily",       "gender": "female", "accent": "Irish",      "description": "Warm, storytelling"},
    # Children
    {"id": "en-US-AnaNeural",        "label": "Ana",         "gender": "child",  "accent": "American",   "description": "Youthful, playful"},
]


class VoiceUpdateRequest(BaseModel):
    voice_id: str

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/books/{book_id}/characters", tags=["characters"])

# Character color palette — warm, rich, distinct
CHARACTER_COLORS = [
    "#E07A5F", "#3D405B", "#81B29A", "#F2CC8F", "#6D597A",
    "#B56576", "#355070", "#EAAC8B", "#56876D", "#E88D67",
    "#5B8E7D", "#BC4749", "#A7C957", "#6A4C93", "#1982C4",
    "#FF595E", "#8AC926", "#FFCA3A", "#6A0572", "#AB83A1",
]

# Cloud models can handle large context; local Ollama needs small chunks
CLOUD_MAX_CHARS = 28000   # ~7k words per chunk — keeps JSON payload under ~30KB (avoids Groq 413)
LOCAL_MAX_CHARS = 12000   # Ollama 8b can handle ~3000 words reliably


def _merge_characters(all_chars: list) -> list:
    """
    Merge duplicate characters detected across multiple chunks.
    Normalises by name, unions aliases/personality, picks highest frequency.
    """
    freq_rank = {"major": 3, "minor": 2, "cameo": 1}
    merged: dict[str, dict] = {}  # key = normalised name

    for char_data in all_chars:
        name = (char_data.get("name") or "").strip()
        if not name:
            continue

        name_key = name.lower()
        aliases_lower = {a.lower() for a in (char_data.get("aliases") or [])}

        # Find if this character already exists under any name/alias
        found_key = None
        for existing_key, existing in merged.items():
            ex_aliases = {a.lower() for a in (existing.get("aliases") or [])}
            if (
                existing_key == name_key
                or name_key in ex_aliases
                or existing_key in aliases_lower
                or (aliases_lower & ex_aliases)   # any alias overlap
            ):
                found_key = existing_key
                break

        if found_key:
            existing = merged[found_key]

            # Keep the highest frequency seen across chunks
            existing_rank = freq_rank.get(existing.get("frequency", "minor"), 2)
            new_rank = freq_rank.get(char_data.get("frequency", "minor"), 2)
            if new_rank > existing_rank:
                existing["frequency"] = char_data["frequency"]

            # Union aliases (deduplicated, case-normalised)
            all_aliases = set(a.lower() for a in (existing.get("aliases") or []))
            all_aliases |= {a.lower() for a in (char_data.get("aliases") or [])}
            # Reconstruct with original casing from first occurrence where possible
            existing["aliases"] = list(all_aliases)

            # Union personality traits (cap at 6)
            existing_p = set(existing.get("personality") or [])
            new_p = set(char_data.get("personality") or [])
            existing["personality"] = list(existing_p | new_p)[:6]

            # Keep more detailed speech_patterns
            existing_sp = existing.get("speech_patterns") or {}
            new_sp = char_data.get("speech_patterns") or {}
            if len(str(new_sp)) > len(str(existing_sp)):
                existing["speech_patterns"] = new_sp

            # Keep longer relationships list
            if len(char_data.get("relationships") or []) > len(existing.get("relationships") or []):
                existing["relationships"] = char_data["relationships"]

        else:
            merged[name_key] = dict(char_data)

    return list(merged.values())


async def _detect_from_chunk(chunk_idx: int, text: str, semaphore: asyncio.Semaphore) -> Optional[dict]:
    """Run character detection on a single text chunk with retry logic."""
    async with semaphore:
        for attempt in range(3):
            try:
                from services.llm.schemas import CharacterDetectionResponse
                client = get_llm_client(role="character_detection")
                prompt = CHARACTER_DETECTION_PROMPT.format(book_text=text)
                result = await client.generate_json(
                    "",
                    prompt,
                    temperature=0.2,   # Low temp for deterministic character facts
                    response_schema=CharacterDetectionResponse,
                )
                if result and isinstance(result, dict) and "characters" in result:
                    logger.info(f"Chunk {chunk_idx}: detected {len(result['characters'])} characters")
                    return result
                logger.warning(f"Chunk {chunk_idx} attempt {attempt+1}: invalid format, retrying…")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Chunk {chunk_idx} attempt {attempt+1} error: {e}")
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
        return None


@router.post("", response_model=list[CharacterResponse])
async def detect_characters(book_id: str, db: Session = Depends(get_db)):
    """Use LLM to detect all characters in a book."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    # Clear existing characters
    db.query(Character).filter(Character.book_id == book_id).delete()

    # Load all chapters and filter out front/back matter
    from services.chapter_filter import filter_story_chapters

    all_chapters = (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id)
        .order_by(Chapter.number)
        .all()
    )

    story_chapters = filter_story_chapters(all_chapters, book.total_chapters)

    # For character detection, use first 8 story chapters (enough to find all characters)
    chapters = story_chapters[:8]

    # Fallback: if filtering removed everything, use all chapters (very short book)
    if not chapters:
        chapters = all_chapters[:5]

    if not chapters:
        raise HTTPException(400, "No chapters found for this book")

    logger.info(
        f"Character detection: using {len(chapters)} story chapters "
        f"(skipped {len(all_chapters) - len(chapters)} non-story chapters)"
    )

    # Determine if we're using a cloud or local provider
    client = get_llm_client(role="character_detection")
    is_local = getattr(client, "is_local", False)
    max_chars_per_chunk = LOCAL_MAX_CHARS if is_local else CLOUD_MAX_CHARS

    logger.info(f"Character detection using {'LOCAL' if is_local else 'CLOUD'} model, "
                f"max {max_chars_per_chunk} chars/chunk")

    # Build text chunks
    full_text = "\n\n".join(
        f"--- {ch.title or f'Chapter {ch.number}'} ---\n\n{ch.raw_text}"
        for ch in chapters
    )

    chunks: list[str] = []
    if len(full_text) <= max_chars_per_chunk:
        # Fits in a single call — best case, no cross-chunk duplication possible
        chunks = [full_text]
    else:
        # Split on paragraph boundaries
        current = ""
        for ch in chapters:
            chapter_text = f"--- {ch.title or f'Chapter {ch.number}'} ---\n\n{ch.raw_text}"
            if current and len(current) + len(chapter_text) > max_chars_per_chunk:
                chunks.append(current)
                current = chapter_text
            else:
                current += ("\n\n" if current else "") + chapter_text
        if current:
            chunks.append(current)

    logger.info(f"Processing {len(chunks)} chunk(s) for character detection")

    # Semaphore: 1 at a time for local (avoid OOM), 3 for cloud
    sem = asyncio.Semaphore(1 if is_local else 3)
    tasks = [_detect_from_chunk(i, chunk, sem) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)

    # Flatten all detected characters
    raw_chars: list[dict] = []
    for i, result in enumerate(results):
        if result and isinstance(result, dict) and "characters" in result:
            raw_chars.extend(result["characters"])
        else:
            logger.warning(f"Chunk {i} returned no usable data")

    if not raw_chars:
        raise HTTPException(500, "No characters detected. Check your LLM provider config.")

    # Merge duplicates that appeared across multiple chunks
    merged_chars = _merge_characters(raw_chars)
    logger.info(f"After merge: {len(raw_chars)} raw → {len(merged_chars)} unique characters")

    # Sort: major first, then minor, then cameo
    freq_rank = {"major": 3, "minor": 2, "cameo": 1}
    merged_chars.sort(key=lambda c: freq_rank.get(c.get("frequency", "minor"), 2), reverse=True)

    # Persist to DB
    characters = []
    for i, char_data in enumerate(merged_chars):
        char = Character(
            book_id=book_id,
            name=char_data.get("name", f"Character {i+1}"),
            aliases=char_data.get("aliases", []),
            gender=char_data.get("gender", "unknown"),
            age_range=char_data.get("age_range", "adult"),
            personality=char_data.get("personality", []),
            speech_patterns=char_data.get("speech_patterns", {}),
            frequency=char_data.get("frequency", "minor"),
            relationships=char_data.get("relationships", []),
            color_hex=CHARACTER_COLORS[i % len(CHARACTER_COLORS)],
        )
        db.add(char)
        characters.append(char)

    db.commit()
    for char in characters:
        db.refresh(char)

    return characters


@router.get("", response_model=list[CharacterResponse])
async def list_characters(book_id: str, db: Session = Depends(get_db)):
    """List all characters for a book."""
    characters = (
        db.query(Character)
        .filter(Character.book_id == book_id)
        .order_by(Character.frequency.desc(), Character.name)
        .all()
    )
    return characters


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character_voice(
    book_id: str,
    character_id: str,
    body: VoiceUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update the voice assignment for a character."""
    char = (
        db.query(Character)
        .filter(Character.id == character_id, Character.book_id == book_id)
        .first()
    )
    if not char:
        raise HTTPException(404, "Character not found")

    # Validate that the voice_id is in our known list
    valid_ids = {v["id"] for v in AVAILABLE_VOICES}
    if body.voice_id not in valid_ids:
        raise HTTPException(400, f"Unknown voice_id: {body.voice_id}")

    char.voice_id = body.voice_id
    db.commit()
    db.refresh(char)
    return char


# ---------------------------------------------------------------------------
# Voices catalogue — separate router prefix for cleanliness
# ---------------------------------------------------------------------------
voices_router = APIRouter(prefix="/api/voices", tags=["voices"])


@voices_router.get("")
async def list_voices():
    """Return the curated list of available TTS voices."""
    return AVAILABLE_VOICES
