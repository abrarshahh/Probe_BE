"""
Markdown output formatter.

Renders the context bundle as a human-readable Markdown file
with fenced code blocks for each source file.
"""

from __future__ import annotations

from app.models.internal import ProjectContext


def render_markdown(context: ProjectContext, summary: str, file_contents: dict[str, str]) -> str:
    """
    Render a ProjectContext and summary as a Markdown string.

    Args:
        context: The aggregated project context.
        summary: The LLM-generated summary.
        file_contents: Mapping of relative path -> file content.

    Returns:
        A complete Markdown document.
    """
    lines: list[str] = []
    
    lines.append(f"# Project Context: {context.name}\n")
    
    lines.append("## AI Summary")
    lines.append(summary)
    lines.append("\n")
    
    lines.append("## Structural Map")
    lines.append("### Directory Tree")
    lines.append("```")
    lines.append(context.directory_tree)
    lines.append("```\n")
    
    if context.entry_points:
        lines.append("### Entry Points")
        for ep in context.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("\n")
        
    if context.dependencies:
        lines.append("### Dependencies")
        for dep in context.dependencies:
            lines.append(f"**{dep.manifest_file}**:")
            if dep.framework_guesses:
                lines.append(f"  Frameworks: {', '.join(dep.framework_guesses)}")
        lines.append("\n")
        
    lines.append("## Source Code Files\n")
    for path, content in file_contents.items():
        lines.append(f"### File: {path}")
        # Find the language for this file
        lang = ""
        for f in context.files:
            if f.path == path:
                lang = f.language or ""
                if f.status == "truncated":
                    lines.append("> **Note:** This file was truncated to fit the token budget.\n")
                break
                
        lines.append(f"```{lang}")
        lines.append(content)
        lines.append("```\n")
        
    return "\n".join(lines)
