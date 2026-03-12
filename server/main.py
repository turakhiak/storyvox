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
from models.database import init_db
from routers import books, characters, screenplay

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")
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
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files (covers, audio)
static_dir = os.path.join(settings.upload_dir, "covers")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static/covers", StaticFiles(directory=static_dir), name="covers")

# Routers
app.include_router(books.router)
app.include_router(characters.router)
app.include_router(screenplay.router)


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
