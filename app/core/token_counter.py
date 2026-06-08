"""
Token Counter — estimate token counts using tiktoken.

Used by Mode A (one-shot) for budget enforcement
and by Mode B (RAG) for chunk sizing.
"""

from __future__ import annotations


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
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Fallback to heuristic if tiktoken is missing or fails
        return estimate_tokens(text)


def estimate_tokens(text: str) -> int:
    """
    Quick heuristic token estimate (chars / 4).

    Use when tiktoken is not available or speed matters more than accuracy.
    """
    return max(1, len(text) // 4)
