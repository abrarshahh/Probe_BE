"""
POST /api/v1/jobs/{job_id}/query — Query a RAG-indexed project (Mode B only).
"""

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.modes.rag import query_rag_index
from app.models.requests import QueryRequest
from app.models.responses import QueryResponse
from app.services.project_manager import project_manager

router = APIRouter()

@router.post("/query/project/{project_id}", response_model=QueryResponse)
async def query_project(project_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query the latest RAG-indexed version of a project with a natural-language question.
    """
    # Look up the latest completed RAG version for this project
    version = await project_manager.get_latest_rag_version(project_id)
    
    if not version:
        raise HTTPException(
            status_code=404, 
            detail="No completed RAG version found for this project. Ensure you have run an analysis in 'rag' mode."
        )

    # Query the RAG index using the discovered version_id
    response = await query_rag_index(version.version_id, request)
    return response


@router.post("/query/version/{version_id}", response_model=QueryResponse)
async def query_version(version_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query a specific RAG-indexed project version.
    """
    # Look up the specific version
    version = await project_manager.get_version(version_id)

    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found.")

    if version.mode != "rag":
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} was created with mode='{version.mode}'. "
                   f"Querying is only available for mode='rag'.",
        )

    if version.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} is not completed yet (status: {version.status}). "
                   f"Wait for indexing to finish before querying.",
        )

    # Query the RAG index
    response = await query_rag_index(version_id, request)
    return response
