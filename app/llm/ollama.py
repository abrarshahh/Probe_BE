"""
Ollama provider — run open models locally with zero cost.
"""

from __future__ import annotations

import logging

import httpx
from app.llm.base import BaseLLMProvider
from app.config import settings

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, model: str | None = None, tier: str = "simple") -> None:
        if model:
            self.model = model
        else:
            self.model = settings.ollama_simple_model if tier == "simple" else settings.ollama_complex_model
        self.base_url = settings.ollama_base_url.rstrip("/")

    @property
    def name(self) -> str:
        return f"ollama/{self.model}"

    async def is_available(self) -> bool:
        """Check if Ollama is running at the configured URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags", timeout=2.0)
                return response.status_code == 200
        except Exception:
            logger.debug("Ollama not reachable at %s", self.base_url)
            return False

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using local Ollama instance."""
        logger.info("Ollama request — model=%s, prompt_len=%d chars, max_tokens=%d", self.model, len(prompt), max_tokens)
        logger.debug("Ollama prompt (first 1000 chars): %s", prompt[:1000])

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens}
                },
                timeout=60.0
            )
            if response.status_code != 200:
                logger.error("Ollama error: status=%d, response=%s", response.status_code, response.text[:500])
                raise RuntimeError(f"Ollama error: status={response.status_code}, response={response.text}")
            
            data = response.json()
            answer = data.get("response", "")
            logger.info("Ollama response — model=%s, response_len=%d chars", self.model, len(answer))
            logger.debug("Ollama response (first 1000 chars): %s", answer[:1000])
            return answer
