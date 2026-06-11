"""
JSON output formatter.

Renders the context bundle as a machine-readable JSON document
for downstream tool consumption.
"""

from __future__ import annotations

import json
import logging

from app.models.internal import ProjectContext

logger = logging.getLogger(__name__)


def render_json(context: ProjectContext, summary: str, file_contents: dict[str, str]) -> str:
    """
    Render a ProjectContext and summary as a JSON string.

    Args:
        context: The aggregated project context.
        summary: The LLM-generated summary.
        file_contents: Mapping of relative path -> file content.

    Returns:
        A JSON string.
    """
    logger.info("Rendering JSON bundle for project: %s", context.name)
    logger.debug(
        "Stats: %d files, %d symbols, %d entry points",
        len(file_contents),
        len(context.symbols),
        len(context.entry_points),
    )
    files_list = []
    for path, content in file_contents.items():
        lang = ""
        is_truncated = False
        file_imports: list[str] = []
        file_exports: list[str] = []
        test_targets: list[str] = []
        for f in context.files:
            if f.path == path:
                lang = f.language or ""
                file_imports = f.imports
                file_exports = f.exports
                test_targets = f.test_targets
                if f.status == "truncated":
                    is_truncated = True
                break
        
        files_list.append({
            "path": path,
            "language": lang,
            "truncated": is_truncated,
            "imports": file_imports,
            "exports": file_exports,
            "test_targets": test_targets,
            "content": content
        })

    # Symbols
    symbols_list = [
        {
            "name": sym.name,
            "kind": sym.kind,
            "file_path": sym.file_path,
            "start_line": sym.start_line,
            "end_line": sym.end_line,
            "signature": sym.signature,
            "parent": sym.parent,
            "docstring": sym.docstring,
        }
        for sym in context.symbols
    ]
        
    output_dict = {
        "project": {
            "name": context.name,
            "ai_summary": summary,
            "structural_map": {
                "directory_tree": context.directory_tree,
                "entry_points": context.entry_points
            },
            "symbols": symbols_list,
            "test_mapping": context.test_mapping,
            "files": files_list
        }
    }
    
    result = json.dumps(output_dict, indent=2)
    logger.info("JSON rendering complete. Generated %d characters", len(result))
    return result
