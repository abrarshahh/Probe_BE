"""
Ollama provider — run open models locally with zero cost.
"""

from __future__ import annotations

import httpx
from app.llm.base import BaseLLMProvider
from app.config import settings


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
            return False

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text using local Ollama instance."""
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
                raise RuntimeError(f"Ollama error: status={response.status_code}, response={response.text}")
            
            data = response.json()
            return data.get("response", "")
