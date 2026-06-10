"""
Symbol Extractor — extract code-level symbols from source files.

Primary: Tree-sitter for multi-language parsing (Python, JS, TS).
Fallback: regex for unsupported languages.

Extracts: classes, functions, methods, interfaces, types, enums,
          constants, imports, exports, docstrings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Language, Parser, Node

from app.models.internal import SymbolRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language loading
# ---------------------------------------------------------------------------

_LANGUAGES: dict[str, Language] = {}
_PARSERS: dict[str, Parser] = {}


def _get_language(lang_key: str) -> Language | None:
    """Lazily load and cache a Tree-sitter Language."""
    if lang_key in _LANGUAGES:
        return _LANGUAGES[lang_key]

    try:
        if lang_key == "python":
            import tree_sitter_python as tspython
            _LANGUAGES[lang_key] = Language(tspython.language())
        elif lang_key == "javascript":
            import tree_sitter_javascript as tsjavascript
            _LANGUAGES[lang_key] = Language(tsjavascript.language())
        elif lang_key == "typescript":
            import tree_sitter_typescript as tstypescript
            _LANGUAGES[lang_key] = Language(tstypescript.language_typescript())
        elif lang_key == "tsx":
            import tree_sitter_typescript as tstypescript
            _LANGUAGES[lang_key] = Language(tstypescript.language_tsx())
        else:
            return None
    except Exception as e:
        logger.warning("Failed to load tree-sitter language %s: %s", lang_key, e)
        return None

    return _LANGUAGES[lang_key]


def _get_parser(lang_key: str) -> Parser | None:
    """Lazily load and cache a Tree-sitter Parser."""
    if lang_key in _PARSERS:
        return _PARSERS[lang_key]

    language = _get_language(lang_key)
    if language is None:
        return None

    parser = Parser(language)
    _PARSERS[lang_key] = parser
    return parser


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Container for all extracted data from a single file."""
    symbols: list[SymbolRecord] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Language mapping
# ---------------------------------------------------------------------------

# Map from our internal language names (from file_classifier) to tree-sitter keys
_LANG_MAP: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "jsx": "javascript",
}


# ---------------------------------------------------------------------------
# Node helpers
# ---------------------------------------------------------------------------

def _node_text(node: Node) -> str:
    """Get the decoded text of a node."""
    return node.text.decode("utf-8") if node.text else ""


def _find_child(node: Node, child_type: str) -> Node | None:
    """Find the first immediate child of a specific type."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _find_child_by_field(node: Node, field_name: str) -> Node | None:
    """Find a child by its field name."""
    return node.child_by_field_name(field_name)


def _get_docstring(node: Node) -> str | None:
    """
    Extract a docstring from a class/function body.
    Looks for the first expression_statement > string in the body block.
    """
    body = _find_child(node, "block") or _find_child(node, "statement_block")
    if body is None:
        return None

    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    raw = _node_text(sub)
                    # Strip surrounding quotes
                    return raw.strip('"\' \n\r')
        # Stop looking after first non-whitespace child
        if child.type not in ("comment", "expression_statement", "newline", "\n"):
            break
    return None


def _get_signature(node: Node, lang_key: str) -> str | None:
    """Extract the function/method signature (the first line)."""
    text = _node_text(node)
    first_line = text.split("\n")[0].rstrip()
    return first_line if first_line else None


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------

def _extract_python(root: Node, file_path: str) -> ExtractionResult:
    """Extract symbols and imports from a Python file."""
    result = ExtractionResult()

    def _visit(node: Node, parent_class: str | None = None) -> None:
        if node.type == "class_definition":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="class",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "python"),
                parent=parent_class,
                docstring=_get_docstring(node),
            ))
            # Visit children with this class as parent
            for child in node.children:
                _visit(child, parent_class=name)
            return

        if node.type == "function_definition":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            kind = "method" if parent_class else "function"
            result.symbols.append(SymbolRecord(
                name=name,
                kind=kind,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "python"),
                parent=parent_class,
                docstring=_get_docstring(node),
            ))
            return  # Don't recurse into nested functions for MVP

        if node.type == "import_statement":
            # e.g. import os
            text = _node_text(node)
            result.imports.append(text.strip())
            return

        if node.type == "import_from_statement":
            # e.g. from pathlib import Path
            text = _node_text(node)
            result.imports.append(text.strip())
            return

        # Recurse into other nodes
        for child in node.children:
            _visit(child, parent_class)

    _visit(root)
    return result


# ---------------------------------------------------------------------------
# JavaScript / TypeScript extractor
# ---------------------------------------------------------------------------

def _extract_js_ts(root: Node, file_path: str) -> ExtractionResult:
    """Extract symbols and imports from a JS/TS file."""
    result = ExtractionResult()

    def _visit(node: Node, parent_class: str | None = None) -> None:
        # Class declarations
        if node.type == "class_declaration":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="class",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "javascript"),
                parent=parent_class,
                docstring=None,
            ))
            for child in node.children:
                _visit(child, parent_class=name)
            return

        # Function declarations
        if node.type in ("function_declaration", "generator_function_declaration"):
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="function",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "javascript"),
                parent=parent_class,
                docstring=None,
            ))
            return

        # Method definitions inside classes
        if node.type == "method_definition":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="method",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "javascript"),
                parent=parent_class,
                docstring=None,
            ))
            return

        # TypeScript-specific: interface, type alias, enum
        if node.type == "interface_declaration":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="interface",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "typescript"),
                parent=None,
                docstring=None,
            ))
            return

        if node.type == "type_alias_declaration":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="type",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "typescript"),
                parent=None,
                docstring=None,
            ))
            return

        if node.type == "enum_declaration":
            name_node = _find_child_by_field(node, "name")
            name = _node_text(name_node) if name_node else "?"
            result.symbols.append(SymbolRecord(
                name=name,
                kind="enum",
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_get_signature(node, "typescript"),
                parent=None,
                docstring=None,
            ))
            return

        # Import statements
        if node.type == "import_statement":
            text = _node_text(node)
            result.imports.append(text.strip())
            return

        # Export statements
        if node.type in ("export_statement",):
            text = _node_text(node)
            result.exports.append(text.strip())
            # Recurse into export to capture the exported declarations
            for child in node.children:
                _visit(child, parent_class)
            return

        # Recurse
        for child in node.children:
            _visit(child, parent_class)

    _visit(root)
    return result


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------

_REGEX_PATTERNS = {
    # Generic patterns for unsupported languages
    "function": re.compile(
        r"^(?:(?:pub(?:lic)?|private|protected|static|async|export)\s+)*"
        r"(?:func(?:tion)?|def|fn)\s+(\w+)",
        re.MULTILINE,
    ),
    "class": re.compile(
        r"^(?:(?:pub(?:lic)?|private|protected|abstract|export)\s+)*"
        r"class\s+(\w+)",
        re.MULTILINE,
    ),
}


def _extract_regex(source: str, file_path: str) -> ExtractionResult:
    """Fallback regex-based extraction for unsupported languages."""
    result = ExtractionResult()
    lines = source.split("\n")

    for match in _REGEX_PATTERNS["class"].finditer(source):
        name = match.group(1)
        line_num = source[: match.start()].count("\n") + 1
        result.symbols.append(SymbolRecord(
            name=name,
            kind="class",
            file_path=file_path,
            start_line=line_num,
            end_line=line_num,
            signature=match.group(0).strip(),
        ))

    for match in _REGEX_PATTERNS["function"].finditer(source):
        name = match.group(1)
        line_num = source[: match.start()].count("\n") + 1
        result.symbols.append(SymbolRecord(
            name=name,
            kind="function",
            file_path=file_path,
            start_line=line_num,
            end_line=line_num,
            signature=match.group(0).strip(),
        ))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_symbols(file_path: Path, language: str | None) -> ExtractionResult:
    """
    Extract symbols from a single source file.

    Args:
        file_path: Absolute path to the source file.
        language: Detected programming language.

    Returns:
        An ExtractionResult containing symbols, imports, and exports.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to read %s: %s", file_path, e)
        return ExtractionResult()

    # Determine tree-sitter language key
    lang_key = _LANG_MAP.get(language or "", None)

    if lang_key:
        parser = _get_parser(lang_key)
        if parser:
            try:
                tree = parser.parse(source.encode("utf-8"))
                if lang_key == "python":
                    return _extract_python(tree.root_node, str(file_path))
                else:
                    return _extract_js_ts(tree.root_node, str(file_path))
            except Exception as e:
                logger.warning(
                    "Tree-sitter extraction failed for %s, falling back to regex: %s",
                    file_path, e,
                )

    # Fallback to regex for unsupported/failed languages
    return _extract_regex(source, str(file_path))
