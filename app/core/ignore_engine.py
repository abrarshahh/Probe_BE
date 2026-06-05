"""
Smart Ignore Engine — decide which files to include, skip, or truncate.

Applies (in order):
1. Built-in ignore patterns for common noise directories and binary files.
2. .gitignore rules (via pathspec).
3. User-specified include/exclude overrides.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pathspec

logger = logging.getLogger(__name__)

# ─── Default ignore directories ───────────────────────────────────────────────

DEFAULT_IGNORE_DIRS: set[str] = {
    ".git", "node_modules", "vendor", "dist", "build",
    ".next", ".nuxt", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cache", "coverage", ".idea", ".vscode", ".tox",
    "eggs", ".eggs", "htmlcov", ".hypothesis", ".svn", ".hg",
    ".terraform", ".serverless", "bower_components",
    ".gradle", ".mvn", "target",  # Java build dirs
}

# ─── Binary file extensions ───────────────────────────────────────────────────

BINARY_EXTENSIONS: set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp", ".tiff",
    # Audio/Video
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg", ".webm",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tgz",
    # Compiled/binary
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib",
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear",
    ".wasm",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Documents (binary formats)
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Database
    ".sqlite", ".db", ".sqlite3", ".mdb",
    # Data/ML
    ".bin", ".dat", ".pkl", ".pickle", ".h5", ".hdf5",
    ".onnx", ".pt", ".pth", ".safetensors", ".gguf",
    # Misc
    ".iso", ".dmg", ".deb", ".rpm",
}

# ─── Generated file patterns ─────────────────────────────────────────────────

GENERATED_FILENAMES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "Cargo.lock",
    "go.sum", "composer.lock", "Gemfile.lock",
}

# Max file size in bytes (default 10 MB)
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024


def _load_gitignore(project_root: Path) -> pathspec.PathSpec | None:
    """Load .gitignore from the project root, if it exists."""
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.is_file():
        return None

    try:
        patterns = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    except Exception:
        logger.warning("Failed to parse .gitignore at %s", gitignore_path, exc_info=True)
        return None


def _build_user_spec(
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> tuple[pathspec.PathSpec | None, pathspec.PathSpec | None]:
    """Build pathspec matchers from user-provided patterns."""
    include_spec = None
    exclude_spec = None

    if include_patterns:
        include_spec = pathspec.PathSpec.from_lines("gitwildmatch", include_patterns)
    if exclude_patterns:
        exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", exclude_patterns)

    return include_spec, exclude_spec


def is_binary_file(path: Path) -> bool:
    """Check if a file is binary by extension or by reading initial bytes."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    # Heuristic: read first 8KB and check for null bytes
    try:
        chunk = path.read_bytes()[:8192]
        if b"\x00" in chunk:
            return True
    except (OSError, PermissionError):
        return True  # Treat unreadable files as binary

    return False


class IgnoreEngine:
    """
    Determines which files and directories should be included or skipped.

    Usage:
        engine = IgnoreEngine(project_root)
        for path in all_paths:
            ignored, reason = engine.should_ignore(path)
    """

    def __init__(
        self,
        project_root: Path,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        self._root = project_root.resolve()
        self._max_file_size = max_file_size
        self._gitignore = _load_gitignore(project_root)
        self._user_include, self._user_exclude = _build_user_spec(
            include_patterns or [], exclude_patterns or []
        )

    def should_ignore_dir(self, dir_path: Path) -> tuple[bool, str | None]:
        """
        Check if a directory should be skipped entirely.

        Returns:
            (should_ignore, reason)
        """
        name = dir_path.name

        # Built-in directory ignores
        if name in DEFAULT_IGNORE_DIRS:
            return True, f"default_ignore_dir:{name}"

        # .gitignore check
        if self._gitignore:
            rel = dir_path.resolve().relative_to(self._root)
            # pathspec expects forward slashes and trailing slash for dirs
            rel_str = rel.as_posix() + "/"
            if self._gitignore.match_file(rel_str):
                return True, "gitignore"

        # User exclude patterns
        if self._user_exclude:
            rel = dir_path.resolve().relative_to(self._root)
            if self._user_exclude.match_file(rel.as_posix() + "/"):
                return True, "user_exclude"

        return False, None

    def should_ignore_file(self, file_path: Path) -> tuple[bool, str | None]:
        """
        Check if a file should be skipped.

        Returns:
            (should_ignore, reason)
        """
        resolved = file_path.resolve()

        try:
            rel = resolved.relative_to(self._root)
        except ValueError:
            return True, "outside_project_root"

        rel_str = rel.as_posix()

        # User include filter: if set, only matching files pass
        if self._user_include and not self._user_include.match_file(rel_str):
            return True, "not_in_user_include"

        # User exclude filter
        if self._user_exclude and self._user_exclude.match_file(rel_str):
            return True, "user_exclude"

        # .gitignore
        if self._gitignore and self._gitignore.match_file(rel_str):
            return True, "gitignore"

        # Binary check (by extension only — full check is done in classifier)
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            return True, "binary_extension"

        # File size check
        try:
            size = file_path.stat().st_size
            if size > self._max_file_size:
                return True, f"too_large:{size}"
            if size == 0:
                return True, "empty_file"
        except OSError:
            return True, "unreadable"

        return False, None

    def scan_directory(self, project_root: Path | None = None) -> tuple[list[Path], list[tuple[Path, str]]]:
        """
        Walk the project tree and return included/skipped files.

        Returns:
            (included_files, skipped_files) where skipped_files is a list
            of (path, reason) tuples.
        """
        root = (project_root or self._root).resolve()
        included: list[Path] = []
        skipped: list[tuple[Path, str]] = []

        for item in sorted(root.rglob("*")):
            if item.is_dir():
                continue  # Dirs are filtered during walk below

            # Check if any parent directory should be ignored
            parent_ignored = False
            for parent in item.relative_to(root).parents:
                if parent == Path("."):
                    continue
                parent_path = root / parent
                ignored, reason = self.should_ignore_dir(parent_path)
                if ignored:
                    parent_ignored = True
                    skipped.append((item, reason or "parent_dir_ignored"))
                    break

            if parent_ignored:
                continue

            ignored, reason = self.should_ignore_file(item)
            if ignored:
                skipped.append((item, reason or "unknown"))
            else:
                included.append(item)

        logger.info(
            "Scan complete: %d included, %d skipped in %s",
            len(included), len(skipped), root,
        )
        return included, skipped
