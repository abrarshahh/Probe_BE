"""
API request schemas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceInput(BaseModel):
    """Describes where the project source lives."""

    type: Literal["github_url", "upload", "local"]
    url: str | None = Field(None, description="GitHub URL or local path")
    branch: str = Field("main", description="Branch, tag, or commit to clone")
    github_token: str | None = Field(None, description="PAT for private repositories")


class AnalyzeOptions(BaseModel):
    """Optional tuning knobs for the analysis pipeline."""

    max_tokens: int = Field(128_000, description="Token budget for one-shot bundles")
    include_patterns: list[str] = Field(default_factory=list, description="Glob patterns to include")
    exclude_patterns: list[str] = Field(default_factory=list, description="Glob patterns to exclude")
    redact_secrets: bool = Field(True, description="Redact detected secrets")


class AnalyzeRequest(BaseModel):
    """Top-level request body for POST /api/v1/projects."""

    project_name: str = Field(..., description="Unique name for the project")
    source: SourceInput
    mode: Literal["one_shot", "rag", "map_reduce"]
    output_format: Literal["markdown", "xml_markdown", "json"] = "markdown"
    options: AnalyzeOptions = Field(default_factory=AnalyzeOptions)


class QueryRequest(BaseModel):
    """Request body for POST /api/v1/jobs/{job_id}/query (Mode B only)."""

    question: str = Field(..., description="Natural-language question about the codebase")
    max_tokens: int = Field(8_000, description="Max tokens in the returned context payload")
    filters: dict[str, str] = Field(default_factory=dict, description="Metadata filters (language, path_prefix, etc.)")
