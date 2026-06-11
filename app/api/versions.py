"""
Version-specific endpoints.
"""

import io
import logging
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.project_manager import project_manager
from app.models.responses import ProjectVersionResponse
from app.core.storage import storage_client

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/versions/project/{project_id}", response_model=list[dict[str, str]])
async def get_project_versions(project_id: str) -> list[dict[str, str]]:
    """Get all versions belonging to a specific project as a list of dicts mapping version number to version ID."""
    logger.info("Listing versions for project: %s", project_id)
    versions = await project_manager.get_versions_for_project(project_id)
    logger.info("Found %d versions for project %s", len(versions), project_id)
    return [{str(v.version_num): str(v.version_id)} for v in versions]

@router.get("/versions/{version_id}", response_model=ProjectVersionResponse)
async def get_version(version_id: str) -> ProjectVersionResponse:
    """Get detailed information for a specific version."""
    logger.info("Fetching version: %s", version_id)
    version = await project_manager.get_version(version_id)
    if not version:
        logger.warning("Version not found: %s", version_id)
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
    return version  # type: ignore[return-value]

@router.get("/versions/{version_id}/download")
async def download_version_markdown(version_id: str):
    """Download the output markdown bundle for a specific version."""
    logger.info("Initiating bundle download for version %s", version_id)
    version = await project_manager.get_version(version_id)
    if not version:
        logger.warning("Download failed — version not found: %s", version_id)
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
        
    if version.status != "completed":
        logger.warning("Download failed — version %s status is '%s', not completed", version_id, version.status)
        raise HTTPException(status_code=400, detail="Version analysis is not completed yet.")

    # We assume bundle.md since the user requested markdown download endpoint
    # Wait, the pipeline saves 'bundle.md' or 'bundle.xml' or 'bundle.json' depending on output_format
    # Let's check what was saved
    project_name = version.project.name
    version_num = version.version_num
    
    object_name = f"{project_name}/v{version_num}/output/bundle.md"
    
    stream = storage_client.get_file_stream(object_name)
    if not stream:
        # It's possible it was run in a non-markdown mode (like json or xml)
        logger.warning("Download failed — markdown bundle object '%s' not found in storage", object_name)
        raise HTTPException(
            status_code=404, 
            detail="Markdown bundle not found. This version may have been run in a different output mode (e.g. JSON or XML)."
        )
        
    logger.info("Streaming markdown bundle download from storage object '%s' started", object_name)
    def stream_generator():
        try:
            for chunk in stream.stream(32768):
                yield chunk
        finally:
            stream.close()
            stream.release_conn()
            
    return StreamingResponse(
        stream_generator(), 
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{project_name}_v{version_num}_bundle.md"'}
    )

@router.get("/versions/{version_id}/download/all")
async def download_version_archive(version_id: str):
    """Download both the output bundle and context.json as a ZIP archive."""
    logger.info("Initiating download archive for version %s", version_id)
    version = await project_manager.get_version(version_id)
    if not version:
        logger.warning("Download archive failed — version not found: %s", version_id)
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
        
    if version.status != "completed":
        logger.warning("Download archive failed — version %s status is '%s', not completed", version_id, version.status)
        raise HTTPException(status_code=400, detail="Version analysis is not completed yet.")

    project_name = version.project.name
    version_num = version.version_num

    # We want to pull files from MinIO prefix: {project_name}/v{version_num}/output/
    prefix = f"{project_name}/v{version_num}/output/"
    try:
        objects = storage_client.client.list_objects(storage_client.bucket, prefix=prefix, recursive=True)
        obj_list = list(objects)
    except Exception as e:
        logger.error("Failed to list S3 objects for version %s: %s", version_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch files from storage.")

    if not obj_list:
        logger.warning("No output files found under prefix %s", prefix)
        raise HTTPException(status_code=404, detail="No output files found for this version.")

    # Create zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for obj in obj_list:
            filename = obj.object_name.split("/")[-1]
            try:
                response = storage_client.client.get_object(storage_client.bucket, obj.object_name)
                data = response.read()
                response.close()
                response.release_conn()
                zip_file.writestr(filename, data)
            except Exception as e:
                logger.error("Failed to read S3 object %s: %s", obj.object_name, e)
                raise HTTPException(status_code=500, detail=f"Failed to read file: {filename}")

    zip_buffer.seek(0)
    
    logger.info("Streaming ZIP download for version %s complete", version_id)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_name}_v{version_num}_output.zip"'}
    )

@router.delete("/versions/{version_id}")
async def delete_project_version(version_id: str) -> dict[str, str]:
    """Delete a specific version of a project from DB, MinIO, and ChromaDB."""
    logger.info("Deleting version: %s", version_id)
    deleted = await project_manager.delete_version(version_id)
    if not deleted:
        logger.warning("Delete failed — version not found: %s", version_id)
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
    logger.info("Version deleted: %s", version_id)
    return {"message": "Version deleted successfully"}
