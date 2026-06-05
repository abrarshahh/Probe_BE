"""
Google Gemini Flash provider — free tier via Google AI Studio.
"""

from __future__ import annotations

from app.llm.base import BaseLLMProvider
from app.config import settings


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Flash LLM provider."""

    @property
    def name(self) -> str:
        return "gemini"

    async def is_available(self) -> bool:
        """Check if GEMINI_API_KEY is set."""
        return bool(settings.gemini_api_key)

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using Gemini Flash."""
        # TODO: Implement google-generativeai SDK call
        raise NotImplementedError
