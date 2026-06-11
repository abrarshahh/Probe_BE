"""
Token Counter — estimate token counts using tiktoken.

Used by Mode A (one-shot) for budget enforcement
and by Mode B (RAG) for chunk sizing.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count tokens in text using tiktoken.

    Args:
        text: The text to count tokens for.
        model: Model name for encoder selection.

    Returns:
        Estimated token count.
    """
    try:
        import tiktoken
        # Try to get the encoding for the model
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to cl100k_base which is standard for most newer models
            logger.debug("Model '%s' not found in tiktoken, falling back to cl100k_base", model)
            encoding = tiktoken.get_encoding("cl100k_base")
        count = len(encoding.encode(text))
        logger.debug("Counted %d tokens (tiktoken) for model %s", count, model)
        return count
    except Exception as e:
        # Fallback to heuristic if tiktoken is missing or fails
        logger.warning(
            "Failed to count tokens with tiktoken for model '%s' (error: %s). Falling back to character heuristic.",
            model,
            e,
        )
        return estimate_tokens(text)


def estimate_tokens(text: str) -> int:
    """
    Quick heuristic token estimate (chars / 4).

    Use when tiktoken is not available or speed matters more than accuracy.
    """
    estimate = max(1, len(text) // 4)
    logger.debug("Estimated %d tokens (heuristic) for %d characters", estimate, len(text))
    return estimate
