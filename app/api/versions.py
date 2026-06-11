"""
Version-specific endpoints.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.project_manager import project_manager
from app.models.responses import ProjectVersionResponse
from app.core.storage import storage_client

router = APIRouter()

@router.get("/versions/project/{project_id}", response_model=list[str])
async def get_project_versions(project_id: str) -> list[str]:
    """Get all version IDs belonging to a specific project."""
    versions = await project_manager.get_versions_for_project(project_id)
    return [v.version_id for v in versions]

@router.get("/versions/{version_id}", response_model=ProjectVersionResponse)
async def get_version(version_id: str) -> ProjectVersionResponse:
    """Get detailed information for a specific version."""
    version = await project_manager.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
    return version  # type: ignore[return-value]

@router.get("/versions/{version_id}/download")
async def download_version_markdown(version_id: str):
    """Download the output markdown bundle for a specific version."""
    version = await project_manager.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
        
    if version.status != "completed":
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
        raise HTTPException(
            status_code=404, 
            detail="Markdown bundle not found. This version may have been run in a different output mode (e.g. JSON or XML)."
        )
        
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

@router.delete("/versions/{version_id}")
async def delete_project_version(version_id: str) -> dict[str, str]:
    """Delete a specific version of a project from DB, MinIO, and ChromaDB."""
    deleted = await project_manager.delete_version(version_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
    return {"message": "Version deleted successfully"}
