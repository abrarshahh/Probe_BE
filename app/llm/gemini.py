"""
Google Gemini Flash provider — free tier via Google AI Studio.
"""

from __future__ import annotations

import logging

import google.generativeai as genai
from app.llm.base import BaseLLMProvider
from app.config import settings

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Flash LLM provider."""

    def __init__(self, model_name: str | None = None, tier: str = "simple") -> None:
        if model_name:
            self.model_name = model_name
        else:
            self.model_name = settings.gemini_simple_model if tier == "simple" else settings.gemini_complex_model
        self._configured = False

    def _ensure_configured(self) -> None:
        if not self._configured:
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set.")
            genai.configure(api_key=settings.gemini_api_key)
            self._configured = True

    @property
    def name(self) -> str:
        return f"gemini/{self.model_name}"

    async def is_available(self) -> bool:
        """Check if GEMINI_API_KEY is set."""
        return bool(settings.gemini_api_key)

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using Gemini Flash."""
        self._ensure_configured()
        
        logger.info("Gemini request — model=%s, prompt_len=%d chars, max_tokens=%d", self.model_name, len(prompt), max_tokens)
        logger.debug("Gemini prompt (first 1000 chars): %s", prompt[:1000])

        # Instantiate model
        model = genai.GenerativeModel(self.model_name)
        
        # Run async generation call
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens
            )
        )
        answer = response.text
        logger.info("Gemini response — model=%s, response_len=%d chars", self.model_name, len(answer))
        logger.debug("Gemini response (first 1000 chars): %s", answer[:1000])
        return answer

