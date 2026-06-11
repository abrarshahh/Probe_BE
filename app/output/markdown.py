"""
Markdown output formatter.

Renders the context bundle as a human-readable Markdown file
with fenced code blocks for each source file.
"""

from __future__ import annotations

import logging

from app.models.internal import ProjectContext

logger = logging.getLogger(__name__)


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
    logger.info("Rendering markdown context bundle for project: %s", context.name)
    logger.debug(
        "Stats: %d files, %d symbols, %d entry points",
        len(file_contents),
        len(context.symbols),
        len(context.entry_points),
    )
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

    # Symbol Index
    if context.symbols:
        lines.append("## Symbol Index\n")
        # Group symbols by file
        symbols_by_file: dict[str, list] = {}
        for sym in context.symbols:
            symbols_by_file.setdefault(sym.file_path, []).append(sym)

        for file_path, syms in symbols_by_file.items():
            lines.append(f"### {file_path}")
            for sym in syms:
                parent_str = f" ({sym.parent})" if sym.parent else ""
                lines.append(
                    f"- `{sym.kind}` **{sym.name}**{parent_str} "
                    f"(lines {sym.start_line}–{sym.end_line})"
                )
            lines.append("")

    # Test-to-Source Mapping
    if context.test_mapping:
        lines.append("## Test Mapping\n")
        for test_file, sources in context.test_mapping.items():
            lines.append(f"- `{test_file}` tests:")
            for src in sources:
                lines.append(f"  - `{src}`")
        lines.append("\n")

    lines.append("## Source Code Files\n")
    for path, content in file_contents.items():
        lines.append(f"### File: {path}")
        # Find the language and imports for this file
        lang = ""
        file_imports: list[str] = []
        for f in context.files:
            if f.path == path:
                lang = f.language or ""
                file_imports = f.imports
                if f.status == "truncated":
                    lines.append("> **Note:** This file was truncated to fit the token budget.\n")
                break

        if file_imports:
            lines.append("**Imports:**")
            for imp in file_imports[:10]:  # Cap at 10 to keep output manageable
                lines.append(f"- `{imp}`")
            if len(file_imports) > 10:
                lines.append(f"- *...and {len(file_imports) - 10} more*")
            lines.append("")

        lines.append(f"```{lang}")
        lines.append(content)
        lines.append("```\n")
        
    result = "\n".join(lines)
    logger.info("Markdown rendering complete. Generated %d characters", len(result))
    return result
