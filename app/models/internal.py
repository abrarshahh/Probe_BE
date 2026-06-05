"""
Internal data models used across the pipeline.
These are NOT exposed via the API directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FileRecord(BaseModel):
    """Metadata about a single file in the project."""

    path: str
    absolute_path: str = ""
    language: str | None = None
    category: Literal[
        "source", "test", "documentation", "configuration",
        "dependency_manifest", "build_deploy", "data", "binary", "generated",
    ] = "source"
    size_bytes: int = 0
    token_count: int | None = None
    status: Literal["included", "truncated", "skipped", "metadata_only"] = "included"
    skip_reason: str | None = None
    is_binary: bool = False
    is_generated: bool = False


class SymbolRecord(BaseModel):
    """A code-level symbol extracted from a source file."""

    name: str
    kind: Literal["class", "function", "method", "interface", "type", "enum", "constant"]
    file_path: str
    start_line: int
    end_line: int
    signature: str | None = None
    parent: str | None = None
    docstring: str | None = None


class DependencyInfo(BaseModel):
    """Parsed dependency information from a manifest file."""

    manifest_file: str
    runtime: list[str] = []
    dev: list[str] = []
    build_tools: list[str] = []
    scripts: dict[str, str] = {}
    framework_guesses: list[str] = []


class ProjectContext(BaseModel):
    """Aggregated context produced by the shared pipeline."""

    name: str = ""
    source_type: str = ""
    source_uri: str = ""
    branch: str = ""
    commit_sha: str = ""
    root_path: str = ""
    primary_languages: list[str] = []
    directory_tree: str = ""
    files: list[FileRecord] = []
    symbols: list[SymbolRecord] = []
    dependencies: list[DependencyInfo] = []
    entry_points: list[str] = []
    skipped_files: list[FileRecord] = []
