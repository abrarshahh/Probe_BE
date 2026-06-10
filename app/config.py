"""
Application settings loaded from environment variables.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings."""

    # --- LLM Providers (Mode C) ---
    # These use their own env var names (no PROBE_ prefix)
    gemini_api_key: str = ""
    gemini_simple_model: str = "gemini-2.5-flash"
    gemini_complex_model: str = "gemini-1.5-pro"
    
    groq_api_key: str = ""
    groq_simple_model: str = "llama-3.1-8b-instant"
    groq_complex_model: str = "llama-3.3-70b-versatile"
    
    ollama_base_url: str = "http://localhost:11434"
    ollama_simple_model: str = "gemma2:2b"
    ollama_complex_model: str = "llama3.1:8b"

    # --- Provider priority ---
    probe_llm_provider: str = "gemini,groq,ollama"

    # --- Storage ---
    output_dir: Path = Path("./outputs")
    db_path: Path = Path("./probe.db")
    chroma_persist_dir: Path = Path("./chroma_db")

    # --- AI Models ---
    embedding_model: str = "all-MiniLM-L6-v2"
    llm_model: str = "gemini/gemini-2.5-flash"

    # --- Limits ---
    max_file_size_mb: int = 10
    max_project_size_mb: int = 500
    max_concurrent_llm_calls: int = 5

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "env_prefix": "",
    }

    @property
    def llm_providers(self) -> list[str]:
        """Return ordered list of LLM provider names."""
        return [p.strip() for p in self.probe_llm_provider.split(",") if p.strip()]


settings = Settings()
