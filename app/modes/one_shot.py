"""
Mode A — One-Shot Context Bundle Builder.

Takes the shared pipeline output and assembles a single LLM-ready file.
Handles token budgeting, file importance ranking, and truncation.

No LLM calls — purely deterministic.
"""

from __future__ import annotations

from app.models.internal import ProjectContext


async def build_one_shot_bundle(
    context: ProjectContext,
    output_format: str,
    max_tokens: int,
) -> str:
    """
    Build a one-shot context bundle from the analyzed project.

    Args:
        context: Aggregated project context from the shared pipeline.
        output_format: "markdown", "xml_markdown", or "json".
        max_tokens: Maximum token budget for the output.

    Returns:
        The assembled bundle content as a string.
    """
    # TODO: Implement token budgeting, ranking, assembly
    raise NotImplementedError
