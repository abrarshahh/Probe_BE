"""
Code Chunker — split source files into semantic chunks for RAG embedding.

Primary strategy: Symbol-aware chunking (one chunk per function/class).
Fallback: Sliding-window token chunks (512 tokens, 128-token overlap).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.token_counter import count_tokens, estimate_tokens
from app.models.internal import FileRecord, SymbolRecord

logger = logging.getLogger(__name__)

# Default chunk parameters
DEFAULT_CHUNK_SIZE = 512       # tokens
DEFAULT_CHUNK_OVERLAP = 128    # tokens
MAX_SYMBOL_CHUNK_TOKENS = 2048 # if a single symbol exceeds this, use sliding window


@dataclass
class CodeChunk:
    """A single chunk of code ready for embedding."""

    text: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    symbol_name: str = ""
    symbol_kind: str = ""
    category: str = "source"  # source, test, documentation, etc.
    chunk_type: str = "symbol"  # "symbol" or "sliding_window"

    @property
    def metadata(self) -> dict[str, str]:
        """Return metadata dict for ChromaDB storage."""
        return {
            "file_path": self.file_path,
            "language": self.language,
            "start_line": str(self.start_line),
            "end_line": str(self.end_line),
            "symbol_name": self.symbol_name,
            "symbol_kind": self.symbol_kind,
            "category": self.category,
            "chunk_type": self.chunk_type,
        }


def chunk_file(
    file_record: FileRecord,
    symbols: list[SymbolRecord],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[CodeChunk]:
    """
    Chunk a single file into embedding-ready pieces.

    Uses symbol boundaries when symbols are available, otherwise
    falls back to a sliding-window approach.

    Args:
        file_record: The file metadata.
        symbols: Symbols extracted from this file.
        chunk_size: Target token count per sliding-window chunk.
        chunk_overlap: Token overlap between adjacent sliding-window chunks.

    Returns:
        List of CodeChunk objects.
    """
    try:
        source = Path(file_record.absolute_path).read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Cannot read %s for chunking: %s", file_record.path, e)
        return []

    if not source.strip():
        return []

    language = file_record.language or ""
    category = file_record.category

    # Filter symbols for this file
    file_symbols = [s for s in symbols if s.file_path == file_record.absolute_path]

    if file_symbols:
        chunks = _chunk_by_symbols(source, file_record, file_symbols, language, category)
        # If symbol chunking produced results, return them
        if chunks:
            return chunks

    # Fallback: sliding window
    return _chunk_sliding_window(
        source, file_record, language, category, chunk_size, chunk_overlap
    )


def _chunk_by_symbols(
    source: str,
    file_record: FileRecord,
    symbols: list[SymbolRecord],
    language: str,
    category: str,
) -> list[CodeChunk]:
    """Split a file by its symbol boundaries."""
    lines = source.split("\n")
    chunks: list[CodeChunk] = []

    # Sort symbols by start line
    sorted_symbols = sorted(symbols, key=lambda s: s.start_line)

    # Track which lines are covered by symbols
    covered_lines: set[int] = set()

    for sym in sorted_symbols:
        start = max(0, sym.start_line - 1)  # 1-indexed to 0-indexed
        end = min(len(lines), sym.end_line)
        chunk_lines = lines[start:end]
        chunk_text = "\n".join(chunk_lines)

        if not chunk_text.strip():
            continue

        # If the symbol is too large, use sliding window on its content
        token_count = estimate_tokens(chunk_text)
        if token_count > MAX_SYMBOL_CHUNK_TOKENS:
            sub_chunks = _chunk_sliding_window(
                chunk_text,
                file_record,
                language,
                category,
                DEFAULT_CHUNK_SIZE,
                DEFAULT_CHUNK_OVERLAP,
                base_line=sym.start_line,
                symbol_name=sym.name,
                symbol_kind=sym.kind,
            )
            chunks.extend(sub_chunks)
        else:
            chunks.append(CodeChunk(
                text=chunk_text,
                file_path=file_record.path,
                language=language,
                start_line=sym.start_line,
                end_line=sym.end_line,
                symbol_name=sym.name,
                symbol_kind=sym.kind,
                category=category,
                chunk_type="symbol",
            ))

        for line_num in range(sym.start_line, sym.end_line + 1):
            covered_lines.add(line_num)

    # Capture any uncovered "preamble" lines (imports, module-level code)
    uncovered_lines = []
    for i, line in enumerate(lines):
        line_num = i + 1
        if line_num not in covered_lines and line.strip():
            uncovered_lines.append((line_num, line))

    if uncovered_lines:
        preamble_text = "\n".join(line for _, line in uncovered_lines)
        if preamble_text.strip():
            chunks.insert(0, CodeChunk(
                text=preamble_text,
                file_path=file_record.path,
                language=language,
                start_line=uncovered_lines[0][0],
                end_line=uncovered_lines[-1][0],
                symbol_name="<module>",
                symbol_kind="",
                category=category,
                chunk_type="preamble",
            ))

    return chunks


def _chunk_sliding_window(
    text: str,
    file_record: FileRecord,
    language: str,
    category: str,
    chunk_size: int,
    chunk_overlap: int,
    base_line: int = 1,
    symbol_name: str = "",
    symbol_kind: str = "",
) -> list[CodeChunk]:
    """Split text using a sliding window based on line counts (approximating tokens)."""
    lines = text.split("\n")

    if not lines:
        return []

    # Estimate lines per chunk (rough: ~4 chars per token, ~40 chars per line => ~10 tokens/line)
    # Use a simpler approach: chunk by lines, aiming for chunk_size tokens
    chunks: list[CodeChunk] = []
    current_start = 0

    while current_start < len(lines):
        # Build chunk greedily until we hit the token limit
        current_end = current_start
        current_text = ""

        while current_end < len(lines):
            candidate = "\n".join(lines[current_start : current_end + 1])
            if estimate_tokens(candidate) > chunk_size and current_end > current_start:
                break
            current_text = candidate
            current_end += 1

        if not current_text.strip():
            current_start = current_end
            continue

        chunks.append(CodeChunk(
            text=current_text,
            file_path=file_record.path,
            language=language,
            start_line=base_line + current_start,
            end_line=base_line + current_end - 1,
            symbol_name=symbol_name,
            symbol_kind=symbol_kind,
            category=category,
            chunk_type="sliding_window",
        ))

        # Advance with overlap
        overlap_lines = max(1, int(chunk_overlap / 10))  # rough: 10 tokens per line
        current_start = max(current_start + 1, current_end - overlap_lines)

    return chunks


def chunk_project(
    files: list[FileRecord],
    symbols: list[SymbolRecord],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[CodeChunk]:
    """
    Chunk all files in a project.

    Args:
        files: All included file records.
        symbols: All extracted symbols.
        chunk_size: Target token count per chunk.
        chunk_overlap: Overlap between sliding-window chunks.

    Returns:
        List of all CodeChunk objects across all files.
    """
    all_chunks: list[CodeChunk] = []

    for f in files:
        if f.is_binary or f.status == "skipped":
            continue
        file_chunks = chunk_file(f, symbols, chunk_size, chunk_overlap)
        all_chunks.extend(file_chunks)

    logger.info(
        "Chunked %d files into %d chunks",
        len(files),
        len(all_chunks),
    )
    return all_chunks
