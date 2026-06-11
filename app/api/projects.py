"""
Project management and analysis endpoints.
"""

from __future__ import annotations

import json
import logging
from typing import Sequence, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form, Query

from app.services.project_manager import project_manager
from app.models.requests import AnalyzeRequest, AnalyzeOptions, SourceInput
from app.models.responses import ProjectListResponse, ProjectDetailResponse, ProjectVersionResponse, AnalyzeResponse
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/projects", response_model=list[ProjectListResponse])
async def list_projects(
    skip: int = Query(0, ge=0, description="Skip N projects"),
    limit: int = Query(10, ge=1, le=100, description="Limit to N projects"),
) -> Any:
    """List all projects and their versions with pagination."""
    logger.info("Listing projects (skip=%d, limit=%d)", skip, limit)
    projects = await project_manager.list_projects(skip=skip, limit=limit)
    response = []
    for p in projects:
        response.append({
            "project_id": p.id,
            "project_name": p.name,
            "number_of_versions": len(p.versions)
        })
    logger.info("Returning %d projects", len(response))
    return response

@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str) -> Any:
    """Get project details."""
    logger.info("Fetching project details for project_id: %s", project_id)
    project = await project_manager.get_project_by_id(project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    
    latest_version = project.versions[0] if project.versions else None
    
    logger.info("Project details successfully retrieved for project: %s", project.name)
    return {
        "project_id": project.id,
        "project_name": project.name,
        "number_of_versions": len(project.versions),
        "mode": latest_version.mode if latest_version else None,
        "status": latest_version.status if latest_version else None,
        "created_at": project.created_at
    }

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str) -> dict[str, str]:
    """Delete a project from DB and wipe its MinIO assets."""
    logger.info("Deleting project: %s", project_id)
    deleted = await project_manager.delete_project(project_id)
    if not deleted:
        logger.warning("Delete failed — project not found: %s", project_id)
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    logger.info("Project deleted: %s", project_id)
    return {"message": "Project deleted successfully"}

@router.get("/projects/status/{job_id}", response_model=ProjectVersionResponse)
async def get_job_status(job_id: str) -> ProjectVersionResponse:
    """Get the status of a specific analysis job (version)."""
    logger.info("Fetching job status for job_id: %s", job_id)
    version = await project_manager.get_version(job_id)
    if not version:
        logger.warning("Job not found: %s", job_id)
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    logger.info("Job status retrieved for job_id: %s (status=%s, phase=%s)", job_id, version.status, version.phase)
    return version  # type: ignore[return-value]

@router.post("/projects/analyze", response_model=AnalyzeResponse)
async def create_project_and_analyze(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """Create a new project and trigger an analysis (Version 1)."""
    
    # Ensure project name is unique
    existing = await project_manager.get_project_by_name(request.project_name)
    if existing:
        raise HTTPException(status_code=400, detail="Project with this name already exists. Use /rerun to analyze again.")

    project = await project_manager.create_project(request.project_name)
    version = await project_manager.create_version(
        project_id=project.id,
        version_num=1,
        mode=request.mode,
        source_type=request.source.type,
        source_uri=request.source.url or "upload",
    )

    logger.info("Project %s (Version 1) created.", project.name)
    
    # Dispatch pipeline
    background_tasks.add_task(run_pipeline, request, project, version, project_manager)

    return AnalyzeResponse(
        job_id=str(version.version_id),
        status="pending",
        message=f"Analysis started. Use GET /api/v1/projects/{str(project.id)} to track status.",
    )

@router.post("/projects/upload", response_model=AnalyzeResponse)
async def upload_project_and_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP archive of the project"),
    project_name: str = Form(...),
    mode: str = Form("one_shot"),
    output_format: str = Form("markdown"),
    options: str = Form("{}"),
) -> AnalyzeResponse:
    """Create a project by uploading a ZIP file."""
    
    existing = await project_manager.get_project_by_name(project_name)
    if existing:
        raise HTTPException(status_code=400, detail="Project with this name already exists.")

    project = await project_manager.create_project(project_name)
    version = await project_manager.create_version(
        project_id=project.id,
        version_num=1,
        mode=mode,
        source_type="upload",
        source_uri=file.filename or "upload.zip",
    )

    # Save locally to temp uploads
    from app.config import settings
    upload_dir = settings.output_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{version.version_id}.zip"
    
    content = await file.read()
    upload_path.write_bytes(content)

    try:
        opts = json.loads(options)
    except json.JSONDecodeError:
        opts = {}

    request = AnalyzeRequest(
        project_name=project_name,
        source=SourceInput(type="upload", url=None, branch="main", github_token=None),
        mode=mode,  # type: ignore[arg-type]
        output_format=output_format,  # type: ignore[arg-type]
        options=AnalyzeOptions(**opts),
    )
    request._upload_path = str(upload_path)  # type: ignore[attr-defined]

    background_tasks.add_task(run_pipeline, request, project, version, project_manager)

    return AnalyzeResponse(
        job_id=str(version.version_id),
        status="pending",
        message=f"Upload received. Use GET /api/v1/projects/{str(project.id)} to track status.",
    )

@router.post("/projects/{project_id}/rerun", response_model=AnalyzeResponse)
async def rerun_project(
    project_id: str,
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalyzeResponse:
    """Trigger a new version analysis for an existing project."""
    
    project = await project_manager.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Determine next version num
    next_version_num = len(project.versions) + 1
    
    version = await project_manager.create_version(
        project_id=project.id,
        version_num=next_version_num,
        mode=request.mode,
        source_type=request.source.type,
        source_uri=request.source.url or "upload",
    )

    # Force request project_name to match
    request.project_name = project.name
    
    background_tasks.add_task(run_pipeline, request, project, version, project_manager)

    return AnalyzeResponse(
        job_id=str(version.version_id),
        status="pending",
        message=f"Rerun started. Version {next_version_num} created.",
    )
