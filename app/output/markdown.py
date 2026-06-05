"""
Markdown output formatter.

Renders the context bundle as a human-readable Markdown file
with fenced code blocks for each source file.
"""

from __future__ import annotations

from app.models.internal import ProjectContext


def render_markdown(context: ProjectContext, file_contents: dict[str, str]) -> str:
    """
    Render a ProjectContext as a Markdown string.

    Args:
        context: The aggregated project context.
        file_contents: Mapping of relative path -> file content.

    Returns:
        A complete Markdown document.
    """
    # TODO: Implement Markdown rendering
    raise NotImplementedError
