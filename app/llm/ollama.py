"""
Ollama provider — run open models locally with zero cost.
"""

from __future__ import annotations

from app.llm.base import BaseLLMProvider
from app.config import settings


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, model: str = "gemma2:2b") -> None:
        self.model = model
        self.base_url = settings.ollama_base_url

    @property
    def name(self) -> str:
        return "ollama"

    async def is_available(self) -> bool:
        """Check if Ollama is running at the configured URL."""
        # TODO: HTTP health check to Ollama server
        raise NotImplementedError

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using local Ollama instance."""
        # TODO: Implement HTTP call to Ollama /api/generate
        raise NotImplementedError
