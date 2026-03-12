from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./storyvox.db"

    # LLM Keys
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"

    # Storage (local filesystem for dev, R2 for prod)
    upload_dir: str = "./uploads"
    audio_dir: str = "./audio_output"

    # CORS
    frontend_url: str = "http://localhost:3000"

    # App
    max_revision_rounds: int = 4
    approval_threshold: float = 7.5

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()

# Ensure directories exist
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.audio_dir, exist_ok=True)
