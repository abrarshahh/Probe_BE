"""
API response schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class JobProgress(BaseModel):
    """Current progress within a running job."""

    phase: str = ""
    files_processed: int = 0
    total_files: int = 0


class JobStatusResponse(BaseModel):
    """Response for GET /api/v1/jobs/{job_id}."""

    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    mode: str
    output_format: str
    created_at: datetime
    completed_at: datetime | None = None
    progress: JobProgress | None = None
    error: str | None = None


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
