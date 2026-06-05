"""
XML-Markdown hybrid output formatter.

Renders the context bundle as an XML document with CDATA-wrapped
code blocks — optimized for structured LLM prompts.
"""

from __future__ import annotations

from app.models.internal import ProjectContext


def render_xml_markdown(context: ProjectContext, file_contents: dict[str, str]) -> str:
    """
    Render a ProjectContext as an XML-Markdown hybrid string.

    Args:
        context: The aggregated project context.
        file_contents: Mapping of relative path -> file content.

    Returns:
        A complete XML document.
    """
    # TODO: Implement XML-Markdown rendering
    raise NotImplementedError
