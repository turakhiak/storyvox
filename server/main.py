"""
StoryVox Backend — FastAPI application entry point.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from models.database import init_db, get_db, Book
from routers import books, characters, screenplay, batch
from routers.characters import voices_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")

    # Reset any batches that were stuck in "processing" state when the server
    # last shut down or crashed.  No background tasks survive a restart, so
    # any "processing" record is definitionally stale.
    try:
        db = next(get_db())
        stuck = db.query(Book).filter(Book.batch_status == "processing").all()
        if stuck:
            logger.warning(
                f"Found {len(stuck)} book(s) with stuck batch_status='processing' — resetting to 'idle'"
            )
            for book in stuck:
                book.batch_status = "idle"
            db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Could not reset stuck batches on startup: {e}")

    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="StoryVox API",
    description="Turn epubs into fully-voiced radio plays",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
        "https://storyvox-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files (covers, audio)
static_dir = os.path.join(settings.upload_dir, "covers")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static/covers", StaticFiles(directory=static_dir), name="covers")

audio_dir = os.path.join(settings.upload_dir, "audio")
os.makedirs(audio_dir, exist_ok=True)
app.mount("/static/audio", StaticFiles(directory=audio_dir), name="audio")

# Routers
app.include_router(books.router)
app.include_router(characters.router)
app.include_router(screenplay.router)
app.include_router(batch.router)
app.include_router(voices_router)


@app.get("/")
async def root():
    return {
        "app": "StoryVox",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
