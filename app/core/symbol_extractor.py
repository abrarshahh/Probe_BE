"""
Symbol Extractor — extract code-level symbols from source files.

Primary: Tree-sitter for multi-language parsing.
Fallback: Python ast for .py files, regex for unsupported languages.

Extracts: classes, functions, methods, interfaces, types, enums,
          constants, imports, exports, docstrings.
"""

from __future__ import annotations

from pathlib import Path

from app.models.internal import SymbolRecord


def extract_symbols(file_path: Path, language: str | None) -> list[SymbolRecord]:
    """
    Extract symbols from a single source file.

    Args:
        file_path: Absolute path to the source file.
        language: Detected programming language.

    Returns:
        A list of SymbolRecord objects found in the file.
    """
    # TODO: Implement Tree-sitter parsing + fallbacks
    raise NotImplementedError
