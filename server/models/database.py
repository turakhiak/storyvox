from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey,
    create_engine, JSON
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func
from config import settings
import uuid

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=True)
    name = Column(String, default="Guest")
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    books = relationship("Book", back_populates="user", cascade="all, delete-orphan")


class Book(Base):
    __tablename__ = "books"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title = Column(String, nullable=False)
    author = Column(String, default="Unknown")
    language = Column(String, default="en")
    cover_url = Column(String, nullable=True)
    epub_path = Column(String, nullable=False)
    total_chapters = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    description = Column(Text, nullable=True)
    status = Column(String, default="imported")  # imported | processing | ready
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="books")
    chapters = relationship("Chapter", back_populates="book", cascade="all, delete-orphan",
                            order_by="Chapter.number")
    characters = relationship("Character", back_populates="book", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String, primary_key=True, default=generate_uuid)
    book_id = Column(String, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    word_count = Column(Integer, default=0)
    status = Column(String, default="parsed")  # parsed | screenplay_ready | audio_ready

    book = relationship("Book", back_populates="chapters")
    screenplays = relationship("Screenplay", back_populates="chapter", cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=generate_uuid)
    book_id = Column(String, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    aliases = Column(JSON, default=list)
    gender = Column(String, nullable=True)
    age_range = Column(String, nullable=True)
    personality = Column(JSON, default=list)
    speech_patterns = Column(JSON, default=dict)
    frequency = Column(String, default="minor")  # major | minor | cameo
    relationships = Column(JSON, default=list)
    color_hex = Column(String, nullable=True)
    voice_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    book = relationship("Book", back_populates="characters")


class Screenplay(Base):
    __tablename__ = "screenplays"

    id = Column(String, primary_key=True, default=generate_uuid)
    chapter_id = Column(String, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    mode = Column(String, nullable=False)  # faithful | radio_play
    status = Column(String, default="processing")
    total_rounds = Column(Integer, default=0)
    final_scores = Column(JSON, nullable=True)
    weighted_avg = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    chapter = relationship("Chapter", back_populates="screenplays")
    segments = relationship("ScreenplaySegment", back_populates="screenplay",
                            cascade="all, delete-orphan", order_by="ScreenplaySegment.order_index")
    revision_rounds = relationship("RevisionRound", back_populates="screenplay",
                                    cascade="all, delete-orphan")


class ScreenplaySegment(Base):
    __tablename__ = "screenplay_segments"

    id = Column(String, primary_key=True, default=generate_uuid)
    screenplay_id = Column(String, ForeignKey("screenplays.id", ondelete="CASCADE"))
    order_index = Column(Integer, nullable=False)
    type = Column(String, nullable=False)  # dialogue | narration | sound_cue
    character_name = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    emotion = Column(String, default="neutral")
    audio_url = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    timestamp_ms = Column(Integer, nullable=True)

    screenplay = relationship("Screenplay", back_populates="segments")


class RevisionRound(Base):
    __tablename__ = "revision_rounds"

    id = Column(String, primary_key=True, default=generate_uuid)
    screenplay_id = Column(String, ForeignKey("screenplays.id", ondelete="CASCADE"))
    round_number = Column(Integer, nullable=False)
    draft = Column(JSON, nullable=False)
    critique = Column(JSON, nullable=False)
    scores = Column(JSON, nullable=False)
    weighted_avg = Column(Float, nullable=True)
    approved = Column(Boolean, default=False)
    is_best = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    screenplay = relationship("Screenplay", back_populates="revision_rounds")


# Database setup
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
