"""
Characters API — detect characters with LLM, list, edit.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db, Book, Chapter, Character
from models.schemas import CharacterResponse
from services.llm.gemini_client import GeminiClient
from services.llm.prompts import CHARACTER_DETECTION_PROMPT
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/books/{book_id}/characters", tags=["characters"])

# Character color palette — warm, rich, distinct
CHARACTER_COLORS = [
    "#E07A5F", "#3D405B", "#81B29A", "#F2CC8F", "#6D597A",
    "#B56576", "#355070", "#EAAC8B", "#56876D", "#E88D67",
    "#5B8E7D", "#BC4749", "#A7C957", "#6A4C93", "#1982C4",
    "#FF595E", "#8AC926", "#FFCA3A", "#6A0572", "#AB83A1",
]


@router.post("", response_model=list[CharacterResponse])
async def detect_characters(book_id: str, db: Session = Depends(get_db)):
    """Use LLM to detect all characters in a book."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(404, "Book not found")

    # Delete existing characters for this book (re-detection)
    db.query(Character).filter(Character.book_id == book_id).delete()

    # Gather text from first 10 chapters (or all if fewer)
    chapters = (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id)
        .order_by(Chapter.number)
        .limit(10)
        .all()
    )

    if not chapters:
        raise HTTPException(400, "No chapters found for this book")

    # Combine chapter text (limit to ~15k chars to fit context)
    combined_text = ""
    for ch in chapters:
        combined_text += f"\n\n--- {ch.title} ---\n\n{ch.raw_text}"
        if len(combined_text) > 15000:
            break

    # Call LLM for character detection
    try:
        client = GeminiClient()
        prompt = CHARACTER_DETECTION_PROMPT.format(book_text=combined_text[:15000])
        result = await client.generate_json("", prompt, temperature=0.3)

        if isinstance(result, dict) and "characters" in result:
            chars_data = result["characters"]
        elif isinstance(result, list):
            chars_data = result
        else:
            raise ValueError(f"Unexpected response format: {type(result)}")

    except Exception as e:
        logger.error(f"Character detection failed: {e}")
        raise HTTPException(500, f"Character detection failed: {str(e)}")

    # Create character records
    characters = []
    for i, char_data in enumerate(chars_data):
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
        .order_by(
            # Major first, then minor, then cameo
            Character.frequency.desc(),
            Character.name
        )
        .all()
    )
    return characters
