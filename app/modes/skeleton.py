"""
Skeleton generator — compiles high-level project map (symbols, directory structure, dependencies)
excluding raw code bodies.
"""

from __future__ import annotations

import logging
from app.models.internal import ProjectContext

logger = logging.getLogger(__name__)

def render_skeleton(context: ProjectContext) -> str:
    """
    Renders the codebase API/surface map as a markdown document.
    """
    logger.info("Generating project skeleton for project: %s", context.name)
    lines: list[str] = []

    # Title
    lines.append(f"# Project Architecture Skeleton: {context.name}\n")

    # Primary Languages
    if context.primary_languages:
        lines.append(f"**Primary Languages:** {', '.join(context.primary_languages)}\n")

    # Directory Structure
    lines.append("## Directory Structure")
    lines.append("```")
    lines.append(context.directory_tree or ".")
    lines.append("```\n")

    # Entry Points
    if context.entry_points:
        lines.append("## Entry Points")
        for ep in context.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("\n")

    # Dependencies
    if context.dependencies:
        lines.append("## Dependencies")
        for dep in context.dependencies:
            lines.append(f"**{dep.manifest_file}**:")
            if dep.framework_guesses:
                lines.append(f"  - Frameworks/Libraries: {', '.join(dep.framework_guesses)}")
            if dep.runtime:
                lines.append(f"  - Runtime deps: {', '.join(dep.runtime[:20])}")
        lines.append("\n")

    # Symbols grouped by file path
    if context.symbols:
        lines.append("## API Surface (Symbols)")
        symbols_by_file: dict[str, list] = {}
        for sym in context.symbols:
            symbols_by_file.setdefault(sym.file_path, []).append(sym)

        for file_path, syms in sorted(symbols_by_file.items()):
            lines.append(f"### File: `{file_path}`")
            for sym in syms:
                parent_str = f" in `{sym.parent}`" if sym.parent else ""
                lines.append(f"- **{sym.kind}** `{sym.name}`{parent_str} (lines {sym.start_line}–{sym.end_line})")
                if sym.signature:
                    lines.append(f"  *Signature:* `{sym.signature}`")
                if sym.docstring:
                    doc = sym.docstring.strip()
                    if doc:
                        # Indent docstring to format nicely under the symbol bullet
                        indented_doc = "\n".join(f"  > {l}" for l in doc.splitlines())
                        lines.append(f"  *Docstring:*\n{indented_doc}")
            lines.append("")

    content = "\n".join(lines)
    logger.info("Skeleton generation complete. Size: %d characters", len(content))
    return content
