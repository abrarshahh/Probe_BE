"""
Test-to-Source Inferencer — build explicit mappings from test files to source files.

Uses a combination of:
1. Import analysis: if test_auth.py imports from app.auth, it maps to app/auth.py.
2. Naming conventions: test_foo.py -> foo.py, foo.test.js -> foo.js.
3. Directory structure: tests/api/test_users.py -> app/api/users.py.
"""

from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath

from app.models.internal import FileRecord

logger = logging.getLogger(__name__)

# Patterns for test file naming conventions
_TEST_FILE_PATTERNS = [
    # Python: test_foo.py -> foo.py
    re.compile(r"^test_(.+)\.py$"),
    # Python: foo_test.py -> foo.py
    re.compile(r"^(.+)_test\.py$"),
    # JS/TS: foo.test.js -> foo.js, foo.spec.ts -> foo.ts
    re.compile(r"^(.+)\.(?:test|spec)\.(js|ts|jsx|tsx)$"),
    # JS/TS: __tests__/foo.js -> foo.js
    re.compile(r"^(.+)\.(js|ts|jsx|tsx)$"),
]

# Common test directory names
_TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}

# Common source directory names
_SOURCE_DIRS = {"src", "app", "lib", "source", "pkg"}


def _normalize_import_to_path(import_str: str) -> str | None:
    """
    Attempt to convert a Python import string to a relative file path.
    e.g., 'from app.core.auth import verify' -> 'app/core/auth.py'
    e.g., 'import app.models.internal' -> 'app/models/internal.py'
    """
    # Handle 'from X import Y'
    from_match = re.match(r"from\s+([\w.]+)\s+import", import_str)
    if from_match:
        module = from_match.group(1)
        return module.replace(".", "/") + ".py"

    # Handle 'import X'
    import_match = re.match(r"import\s+([\w.]+)", import_str)
    if import_match:
        module = import_match.group(1)
        return module.replace(".", "/") + ".py"

    return None


def _normalize_js_import_to_path(import_str: str) -> str | None:
    """
    Attempt to extract a relative path from a JS/TS import.
    e.g., "import { foo } from './auth'" -> 'auth'
    e.g., "import auth from '../lib/auth'" -> 'lib/auth'
    """
    match = re.search(r"""(?:from|require\()\s*['"](\.\.?/.+?)['"]""", import_str)
    if match:
        return match.group(1)
    return None


def infer_test_mapping(
    files: list[FileRecord],
) -> dict[str, list[str]]:
    """
    Build an explicit test-to-source mapping.

    Args:
        files: All file records (including test and source files).

    Returns:
        Dict mapping test file paths to lists of source file paths they test.
    """
    logger.info("Inferring test-to-source mapping for project...")
    # Build lookup sets
    all_paths = {f.path for f in files}
    source_paths = {f.path for f in files if f.category == "source"}
    logger.debug("Test inference base: %d total source files", len(source_paths))

    test_mapping: dict[str, list[str]] = {}

    for f in files:
        if f.category != "test":
            continue

        targets: list[str] = []
        test_path = PurePosixPath(f.path)

        # --- Strategy 1: Import analysis ---
        for imp in f.imports:
            normalized = None
            if f.language == "python":
                normalized = _normalize_import_to_path(imp)
            elif f.language in ("javascript", "typescript", "jsx", "tsx"):
                normalized = _normalize_js_import_to_path(imp)

            if normalized and normalized in source_paths:
                targets.append(normalized)

        # --- Strategy 2: Naming convention ---
        stem = test_path.stem
        suffix = test_path.suffix

        # Python: test_foo.py -> foo.py
        if stem.startswith("test_"):
            candidate_name = stem[5:] + suffix
            _search_candidate(candidate_name, test_path, source_paths, targets)

        # Python: foo_test.py -> foo.py
        if stem.endswith("_test"):
            candidate_name = stem[:-5] + suffix
            _search_candidate(candidate_name, test_path, source_paths, targets)

        # JS/TS: foo.test.js -> foo.js, foo.spec.ts -> foo.ts
        for pattern in (r"(.+)\.(?:test|spec)$",):
            m = re.match(pattern, stem)
            if m:
                candidate_name = m.group(1) + suffix
                _search_candidate(candidate_name, test_path, source_paths, targets)

        # --- Strategy 3: Directory structure mirroring ---
        # tests/api/test_users.py -> app/api/users.py or src/api/users.py
        parts = list(test_path.parts)
        for i, part in enumerate(parts):
            if part in _TEST_DIRS:
                # Replace test dir with possible source dirs
                for src_dir in _SOURCE_DIRS:
                    candidate_parts = list(parts)
                    candidate_parts[i] = src_dir

                    # Also strip test_ prefix from filename
                    filename = candidate_parts[-1]
                    if filename.startswith("test_"):
                        candidate_parts[-1] = filename[5:]

                    candidate = "/".join(candidate_parts)
                    if candidate in source_paths and candidate not in targets:
                        targets.append(candidate)

        # Deduplicate and store
        if targets:
            dedup_targets = list(dict.fromkeys(targets))  # preserve order, dedup
            logger.info("Mapped test file '%s' to source files: %s", f.path, dedup_targets)
            test_mapping[f.path] = dedup_targets

    logger.info("Test-to-source mapping complete. Mapped %d test files.", len(test_mapping))
    return test_mapping


def _search_candidate(
    candidate_name: str,
    test_path: PurePosixPath,
    source_paths: set[str],
    targets: list[str],
) -> None:
    """Search for a source file candidate matching a test file's naming convention."""
    # Look in the same directory
    candidate = str(test_path.parent / candidate_name)
    if candidate in source_paths and candidate not in targets:
        targets.append(candidate)

    # Look in source directories
    parts = list(test_path.parts)
    for i, part in enumerate(parts):
        if part in _TEST_DIRS:
            for src_dir in _SOURCE_DIRS:
                candidate_parts = list(parts)
                candidate_parts[i] = src_dir
                candidate_parts[-1] = candidate_name
                candidate = "/".join(candidate_parts)
                if candidate in source_paths and candidate not in targets:
                    targets.append(candidate)
