"""
Abstract base class for LLM providers.

All providers must implement the `generate` method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Abstract LLM provider interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        ...

    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: The input prompt.
            max_tokens: Maximum tokens in the response.

        Returns:
            The generated text.
        """
        ...


async def get_available_provider(provider_order: list[str], tier: str = "simple") -> BaseLLMProvider:
    """
    Return the first available LLM provider from the priority list.

    Args:
        provider_order: List of provider names to try in order.
        tier: "simple" or "complex" to select the appropriate model.

    Returns:
        An initialized, available provider.

    Raises:
        RuntimeError: If no provider is available.
    """
    from app.llm.gemini import GeminiProvider
    from app.llm.groq import GroqProvider
    from app.llm.ollama import OllamaProvider

    for p in provider_order:
        p_lower = p.lower().strip()
        if not p_lower:
            continue

        provider: BaseLLMProvider
        parts = p_lower.split("/", 1)
        provider_type = parts[0]
        model_name = parts[1] if len(parts) > 1 else None

        if provider_type == "gemini":
            provider = GeminiProvider(model_name, tier=tier) if model_name else GeminiProvider(tier=tier)
        elif provider_type == "groq":
            provider = GroqProvider(model_name, tier=tier) if model_name else GroqProvider(tier=tier)
        elif provider_type == "ollama":
            provider = OllamaProvider(model_name, tier=tier) if model_name else OllamaProvider(tier=tier)
        else:
            continue

        if await provider.is_available():
            return provider

    raise RuntimeError(f"No LLM provider is available from the list: {provider_order}")
