"""
Groq provider — free tier with open models (Llama 3, Gemma).
"""

from __future__ import annotations

from app.llm.base import BaseLLMProvider
from app.config import settings


class GroqProvider(BaseLLMProvider):
    """Groq Cloud LLM provider."""

    @property
    def name(self) -> str:
        return "groq"

    async def is_available(self) -> bool:
        """Check if GROQ_API_KEY is set."""
        return bool(settings.groq_api_key)

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using Groq API."""
        # TODO: Implement groq SDK call
        raise NotImplementedError
