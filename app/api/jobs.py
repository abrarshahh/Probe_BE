"""
GET/DELETE /api/v1/jobs/{job_id} — Job status and management.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.deps import get_job_manager
from app.models.responses import JobStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Check the status of an analysis job."""
    jm = get_job_manager()
    job = await jm.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return job


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """Download the generated output artifact for a completed job."""
    jm = get_job_manager()
    job = await jm.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job.status}",
        )

    result_path = await jm.get_result_path(job_id)
    if not result_path or not Path(result_path).is_file():
        raise HTTPException(
            status_code=404,
            detail="Result file not found. The job may not have produced an output.",
        )

    path = Path(result_path)
    media_type_map = {
        ".md": "text/markdown",
        ".xml": "application/xml",
        ".json": "application/json",
    }
    media_type = media_type_map.get(path.suffix, "text/plain")

    return FileResponse(
        path=result_path,
        filename=path.name,
        media_type=media_type,
    )


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict[str, str]:
    """Delete a job and its artifacts."""
    jm = get_job_manager()

    deleted = await jm.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Also clean up output directory
    from app.config import settings
    import shutil

    output_dir = settings.output_dir / job_id
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)

    logger.info("Job %s deleted", job_id)
    return {"message": f"Job {job_id} deleted successfully."}
