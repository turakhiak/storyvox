from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./storyvox.db"

    # Azure Speech TTS (optional — free tier: 500K chars/month, no credit card needed)
    # Create resource at: portal.azure.com → Create Speech resource → F0 (free) tier
    azure_speech_key: Optional[str] = None
    azure_speech_region: str = "eastus"

    # LLM Keys & Models
    gemini_api_key: Optional[str] = None
    # ALL 1.x and 2.0 models RETIRED as of March 3, 2026 (404 errors)
    # gemini-2.5-flash-lite: 15 RPM, 1,000 req/day free — fast, cheap, best for simple tasks
    # gemini-2.5-flash:      10 RPM,   250 req/day free — higher quality for creative writing
    gemini_model: str = "gemini-2.5-flash-lite"      # Simple tasks: character detection, general
    gemini_model_quality: str = "gemini-2.5-flash"   # Creative tasks: screenplay writer/director
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    primary_provider: str = "gemini" # gemini | groq
    use_fallback: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_num_ctx: int = 32768  # Raised from 4096 — pipeline needs ~10k+ tokens per chunk

    # Screenplay chunk sizes — cloud models support much larger context windows
    screenplay_chunk_size_cloud: int = 30000  # ~7500 words per chunk for Gemini/Groq
    screenplay_chunk_size_local: int = 3000   # Conservative for Ollama 3b models

    # Sound Effects (Freesound.org — free API, register at freesound.org/apiv2/apply/)
    freesound_api_key: Optional[str] = None

    # Storage (local filesystem for dev, R2 for prod)
    upload_dir: str = "./uploads"
    audio_dir: str = "./audio_output"

    # CORS
    frontend_url: str = "http://localhost:3000"

    # App
    max_revision_rounds: int = 4
    approval_threshold: float = 7.5
    batch_size: int = 5  # Number of chapters to process at a time

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()

# Ensure directories exist
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.audio_dir, exist_ok=True)
