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


async def get_available_provider(provider_order: list[str]) -> BaseLLMProvider:
    """
    Return the first available LLM provider from the priority list.

    Args:
        provider_order: List of provider names to try in order.

    Returns:
        An initialized, available provider.

    Raises:
        RuntimeError: If no provider is available.
    """
    # TODO: Import and check each provider
    raise NotImplementedError("No LLM provider available")
