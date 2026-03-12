from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class BookResponse(BaseModel):
    id: str
    title: str
    author: str
    language: str
    cover_url: Optional[str] = None
    total_chapters: int
    total_words: int
    description: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChapterResponse(BaseModel):
    id: str
    book_id: str
    number: int
    title: Optional[str] = None
    word_count: int
    status: str
    raw_text: Optional[str] = None  # Only included when fetching single chapter

    class Config:
        from_attributes = True


class ChapterListResponse(BaseModel):
    id: str
    book_id: str
    number: int
    title: Optional[str] = None
    word_count: int
    status: str

    class Config:
        from_attributes = True


class CharacterResponse(BaseModel):
    id: str
    book_id: str
    name: str
    aliases: list = []
    gender: Optional[str] = None
    age_range: Optional[str] = None
    personality: list = []
    speech_patterns: dict = {}
    frequency: str = "minor"
    relationships: list = []
    color_hex: Optional[str] = None
    voice_id: Optional[str] = None

    class Config:
        from_attributes = True


class ScreenplaySegmentResponse(BaseModel):
    id: str
    order_index: int
    type: str
    character_name: Optional[str] = None
    text: str
    emotion: str = "neutral"

    class Config:
        from_attributes = True


class ScreenplayResponse(BaseModel):
    id: str
    chapter_id: str
    mode: str
    status: str
    total_rounds: int
    final_scores: Optional[dict] = None
    weighted_avg: Optional[float] = None
    segments: list[ScreenplaySegmentResponse] = []

    class Config:
        from_attributes = True


class RevisionRoundResponse(BaseModel):
    id: str
    round_number: int
    scores: dict
    weighted_avg: Optional[float] = None
    approved: bool
    is_best: bool
    critique: dict

    class Config:
        from_attributes = True


class ProcessingStatusResponse(BaseModel):
    book_id: str
    total_chapters: int
    chapters_processed: int
    current_chapter: Optional[str] = None
    current_round: Optional[int] = None
    status: str  # idle | processing | complete


class ErrorResponse(BaseModel):
    detail: str
