"""
JSON output formatter.

Renders the context bundle as a machine-readable JSON document
for downstream tool consumption.
"""

from __future__ import annotations

from app.models.internal import ProjectContext


def render_json(context: ProjectContext, file_contents: dict[str, str]) -> str:
    """
    Render a ProjectContext as a JSON string.

    Args:
        context: The aggregated project context.
        file_contents: Mapping of relative path -> file content.

    Returns:
        A JSON string.
    """
    # TODO: Implement JSON rendering
    raise NotImplementedError
