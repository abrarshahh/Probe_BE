"""
POST /api/v1/jobs/{job_id}/query — Query a RAG-indexed project (Mode B only).
"""

from fastapi import APIRouter, HTTPException

from app.models.requests import QueryRequest
from app.models.responses import QueryResponse

router = APIRouter()


@router.post("/jobs/{job_id}/query", response_model=QueryResponse)
async def query_project(job_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query a RAG-indexed project with a natural-language question.
    Only available for jobs created with mode='rag'.
    """
    # TODO: Embed question, retrieve from ChromaDB, assemble context
    raise NotImplementedError("Query endpoint not yet implemented")
