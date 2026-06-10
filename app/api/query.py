"""
POST /api/v1/jobs/{job_id}/query — Query a RAG-indexed project (Mode B only).
"""

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.modes.rag import query_rag_index
from app.models.requests import QueryRequest
from app.models.responses import QueryResponse
from app.services.job_manager import JobManager

router = APIRouter()


@router.post("/jobs/{job_id}/query", response_model=QueryResponse)
async def query_project(job_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query a RAG-indexed project with a natural-language question.
    Only available for jobs created with mode='rag'.
    """
    # 1. Look up the job
    job_manager = JobManager(settings.db_path)
    job = await job_manager.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    if job.mode != "rag":
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} was created with mode='{job.mode}'. "
                   f"Querying is only available for mode='rag' jobs.",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is not completed yet (status: {job.status}). "
                   f"Wait for indexing to finish before querying.",
        )

    # 2. Query the RAG index
    response = await query_rag_index(job_id, request)
    return response
