"""
POST /api/v1/analyze — Submit a new analysis job.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form

from app.deps import get_job_manager
from app.models.requests import AnalyzeRequest, AnalyzeOptions, SourceInput
from app.models.responses import AnalyzeResponse
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def submit_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """
    Submit a new codebase analysis job.

    Accepts a GitHub URL, selects one of three modes
    (one_shot, rag, map_reduce), and starts the analysis
    pipeline in the background.
    """
    jm = get_job_manager()

    job_id = await jm.create_job(
        mode=request.mode,
        output_format=request.output_format,
        source_type=request.source.type,
        source_uri=request.source.url or "upload",
    )

    logger.info(
        "Job %s created: mode=%s, format=%s, source=%s",
        job_id, request.mode, request.output_format, request.source.type,
    )

    # Dispatch the pipeline as a background task
    background_tasks.add_task(run_pipeline, request, job_id, jm)

    return AnalyzeResponse(
        job_id=job_id,
        status="pending",
        message=f"Analysis job created. Use GET /api/v1/jobs/{job_id} to check status.",
    )


@router.post("/analyze/upload", response_model=AnalyzeResponse)
async def submit_analysis_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP archive of the project"),
    mode: str = Form("one_shot"),
    output_format: str = Form("markdown"),
    options: str = Form("{}"),
) -> AnalyzeResponse:
    """
    Submit an analysis job by uploading a ZIP file.

    The ZIP is saved to the workspace and extracted during pipeline execution.
    """
    jm = get_job_manager()

    job_id = await jm.create_job(
        mode=mode,
        output_format=output_format,
        source_type="upload",
        source_uri=file.filename or "upload.zip",
    )

    # Save uploaded file to a temp location
    from app.config import settings
    upload_dir = settings.output_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{job_id}.zip"

    content = await file.read()
    upload_path.write_bytes(content)

    logger.info("Job %s: upload saved to %s (%d bytes)", job_id, upload_path, len(content))

    # Parse options
    try:
        opts = json.loads(options)
    except json.JSONDecodeError:
        opts = {}

    request = AnalyzeRequest(
        source=SourceInput(type="upload"),
        mode=mode,  # type: ignore[arg-type]
        output_format=output_format,  # type: ignore[arg-type]
        options=AnalyzeOptions(**opts),
    )

    # We need to pass the upload path to the pipeline
    # Store it as a custom attribute on the request for now
    request._upload_path = str(upload_path)  # type: ignore[attr-defined]

    background_tasks.add_task(run_pipeline, request, job_id, jm)

    return AnalyzeResponse(
        job_id=job_id,
        status="pending",
        message=f"Upload received. Use GET /api/v1/jobs/{job_id} to check status.",
    )
