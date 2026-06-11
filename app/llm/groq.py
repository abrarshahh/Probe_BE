"""
Groq provider — free tier with open models (Llama 3, Gemma).
"""

from __future__ import annotations

import logging

from groq import AsyncGroq
from app.llm.base import BaseLLMProvider
from app.config import settings

logger = logging.getLogger(__name__)


class GroqProvider(BaseLLMProvider):
    """Groq Cloud LLM provider."""

    def __init__(self, model_name: str | None = None, tier: str = "simple") -> None:
        if model_name:
            self.model_name = model_name
        else:
            self.model_name = settings.groq_simple_model if tier == "simple" else settings.groq_complex_model
        self._client: AsyncGroq | None = None

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is not set.")
            self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    @property
    def name(self) -> str:
        return f"groq/{self.model_name}"

    async def is_available(self) -> bool:
        """Check if GROQ_API_KEY is set."""
        return bool(settings.groq_api_key)

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using Groq API."""
        client = self._get_client()
        
        logger.info("Groq request — model=%s, prompt_len=%d chars, max_tokens=%d", self.model_name, len(prompt), max_tokens)
        logger.debug("Groq prompt (first 1000 chars): %s", prompt[:1000])

        completion = await client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
        )
        content = completion.choices[0].message.content or ""
        logger.info("Groq response — model=%s, response_len=%d chars", self.model_name, len(content))
        logger.debug("Groq response (first 1000 chars): %s", content[:1000])
        return content
