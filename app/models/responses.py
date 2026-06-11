"""
API response schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VersionProgress(BaseModel):
    """Current progress within a running version analysis."""

    phase: str = ""
    files_processed: int = 0
    total_files: int = 0

class ProjectVersionResponse(BaseModel):
    """Response for a specific project version."""

    version_id: str
    version_num: int
    status: Literal["pending", "processing", "completed", "failed"]
    mode: str
    source_type: str
    source_uri: str
    created_at: datetime
    completed_at: datetime | None = None
    progress: VersionProgress | None = None
    error: str | None = None

class ProjectListResponse(BaseModel):
    """Summarized project info for lists."""
    project_id: str
    project_name: str
    number_of_versions: int

class ProjectDetailResponse(BaseModel):
    """Detailed response for a single project."""
    project_id: str
    project_name: str
    number_of_versions: int
    mode: str | None = None
    status: str | None = None
    created_at: datetime


class AnalyzeResponse(BaseModel):
    """Response for POST /api/v1/analyze — returned immediately."""

    job_id: str
    status: str = "pending"
    message: str = "Analysis job created successfully."


class QuerySource(BaseModel):
    """A single source chunk returned from a RAG query."""

    file: str
    lines: str
    relevance: float


class QueryResponse(BaseModel):
    """Response for POST /api/v1/jobs/{job_id}/query."""

    answer: str = ""
    context_payload: str
    sources: list[QuerySource] = Field(default_factory=list)
    token_count: int = 0
    structural_map_included: bool = True
