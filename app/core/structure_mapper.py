"""
Structure Mapper — generate the project skeleton.

Produces:
- Directory tree (ASCII visual format).
- Entry-point candidates.
- File inventory grouped by category.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from app.models.internal import FileRecord

logger = logging.getLogger(__name__)

# ─── Entry point patterns ────────────────────────────────────────────────────

ENTRY_POINT_PATTERNS: dict[str, list[str]] = {
    "python": [
        "main.py", "app.py", "manage.py", "run.py",
        "wsgi.py", "asgi.py", "server.py", "cli.py",
        "__main__.py",
        "src/main.py", "src/app.py",
        "app/main.py", "app/app.py",
    ],
    "javascript": [
        "index.js", "server.js", "app.js", "main.js",
        "src/index.js", "src/main.js", "src/app.js",
        "src/server.js",
    ],
    "typescript": [
        "index.ts", "server.ts", "app.ts", "main.ts",
        "src/index.ts", "src/main.ts", "src/app.ts",
        "src/server.ts", "src/App.tsx", "src/main.tsx",
    ],
    "go": [
        "main.go", "cmd/main.go",
    ],
    "rust": [
        "src/main.rs", "src/lib.rs",
    ],
    "java": [
        "src/main/java/**/Application.java",
        "src/main/java/**/Main.java",
    ],
    "csharp": [
        "Program.cs",
    ],
}


def generate_directory_tree(
    project_root: Path,
    files: list[FileRecord],
    max_depth: int = 6,
    max_entries: int = 200,
) -> str:
    """
    Generate an ASCII directory tree representation.

    Args:
        project_root: Root directory of the project.
        files: List of classified file records (included + skipped for completeness).
        max_depth: Maximum depth of the tree.
        max_entries: Maximum number of entries to show (truncates with '...').

    Returns:
        A string containing the visual directory tree.
    """
    # Build a set of all directories and files from the file records
    dirs: set[str] = set()
    file_paths: set[str] = set()

    for f in files:
        file_paths.add(f.path)
        # Add all parent directories
        parts = Path(f.path).parts
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))

    # Sort everything for deterministic output
    all_entries: list[tuple[str, bool]] = []  # (path, is_dir)
    for d in sorted(dirs):
        depth = d.count("/") + 1
        if depth <= max_depth:
            all_entries.append((d, True))
    for f in sorted(file_paths):
        depth = f.count("/")
        if depth <= max_depth:
            all_entries.append((f, False))

    # Build tree lines using prefix-based rendering
    root_name = project_root.name or "."
    lines: list[str] = [root_name + "/"]
    entry_count = 0

    # Group entries by parent for proper tree rendering
    children: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for path, is_dir in all_entries:
        parent = str(Path(path).parent)
        if parent == ".":
            parent = ""
        children[parent].append((path, is_dir))

    def _render(parent: str, prefix: str) -> None:
        nonlocal entry_count
        items = children.get(parent, [])
        # Sort: directories first, then files, alphabetically
        items.sort(key=lambda x: (not x[1], x[0]))

        for i, (path, is_dir) in enumerate(items):
            if entry_count >= max_entries:
                lines.append(f"{prefix}└── ... ({len(all_entries) - entry_count} more)")
                entry_count = len(all_entries)
                return

            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            name = Path(path).name
            display = name + "/" if is_dir else name
            lines.append(f"{prefix}{connector}{display}")
            entry_count += 1

            if is_dir:
                extension = "    " if is_last else "│   "
                _render(path, prefix + extension)

    _render("", "")

    return "\n".join(lines)


def detect_entry_points(files: list[FileRecord]) -> list[str]:
    """
    Identify likely entry-point files.

    Looks for well-known filename patterns across languages.

    Returns:
        List of relative paths to entry-point candidates.
    """
    file_paths = {f.path for f in files if f.status == "included"}
    entry_points: list[str] = []

    for _lang, patterns in ENTRY_POINT_PATTERNS.items():
        for pattern in patterns:
            if "**" in pattern:
                # Wildcard pattern — check suffix
                suffix = pattern.split("**/")[-1]
                for fp in file_paths:
                    if fp.endswith(suffix):
                        entry_points.append(fp)
            elif pattern in file_paths:
                entry_points.append(pattern)

    # Also check for package.json scripts.start, pyproject.toml scripts, etc.
    # (handled by dependency analyzer, not here)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for ep in entry_points:
        if ep not in seen:
            seen.add(ep)
            unique.append(ep)

    logger.info("Detected %d entry point candidates", len(unique))
    return unique


def build_file_inventory(files: list[FileRecord]) -> dict[str, list[str]]:
    """
    Group files by category for a summary view.

    Returns:
        Dict mapping category name to list of file paths.
    """
    inventory: dict[str, list[str]] = defaultdict(list)
    for f in files:
        inventory[f.category].append(f.path)

    # Sort files within each category
    for category in inventory:
        inventory[category].sort()

    return dict(inventory)
