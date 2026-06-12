"""
Query endpoints — RAG querying for projects and versions.
"""

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.modes.rag import query_rag_index, retrieve_context_payload
from app.modes.skeleton import render_skeleton
from app.models.requests import QueryRequest
from app.models.responses import QueryResponse
from app.models.internal import ProjectContext
from app.services.project_manager import project_manager
from app.core.storage import storage_client

logger = logging.getLogger(__name__)

router = APIRouter()

async def _fetch_version_files(project_name: str, version_num: int) -> dict[str, tuple[int, int | None]] | None:
    object_name = f"{project_name}/v{version_num}/output/context.json"
    try:
        context_dict = storage_client.client.get_object(storage_client.bucket, object_name)
        data = json.loads(context_dict.read().decode("utf-8"))
        context_dict.close()
        context_dict.release_conn()
        
        files_dict = {}
        for f in data.get("files", []):
            files_dict[f["path"]] = (f.get("size_bytes", 0), f.get("token_count"))
        return files_dict
    except Exception as e:
        logger.warning("Failed to fetch context files for %s v%d: %s", project_name, version_num, e)
        return None


def _compute_version_diffs(
    completed_versions_files: list[tuple[int, dict[str, tuple[int, int | None]]]]
) -> str:
    if len(completed_versions_files) < 2:
        return ""
        
    diff_lines = ["## File Differences between Versions\n"]
    for idx in range(len(completed_versions_files) - 1):
        v_old_num, old_files = completed_versions_files[idx]
        v_new_num, new_files = completed_versions_files[idx + 1]
        
        added = []
        deleted = []
        modified = []
        
        for path in new_files:
            if path not in old_files:
                added.append(path)
            else:
                old_size, old_tokens = old_files[path]
                new_size, new_tokens = new_files[path]
                if old_size != new_size or old_tokens != new_tokens:
                    modified.append(path)
                    
        for path in old_files:
            if path not in new_files:
                deleted.append(path)
                
        diff_lines.append(f"### Version {v_new_num} vs Version {v_old_num}")
        changes_found = False
        if added:
            diff_lines.append(f"- **Added Files:** " + ", ".join(f"`{f}`" for f in added))
            changes_found = True
        if deleted:
            diff_lines.append(f"- **Deleted Files:** " + ", ".join(f"`{f}`" for f in deleted))
            changes_found = True
        if modified:
            diff_lines.append(f"- **Modified Files:** " + ", ".join(f"`{f}`" for f in modified))
            changes_found = True
        if not changes_found:
            diff_lines.append("- No file changes detected between these versions.")
        diff_lines.append("")
        
    return "\n".join(diff_lines)


@router.post("/query/project/{project_id}", response_model=QueryResponse)
async def query_project(project_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query the latest RAG-indexed version of a project with a natural-language question.
    """
    # Look up the latest completed RAG version for this project
    logger.info("Querying project %s: '%s'", project_id, request.question[:100])
    
    # 1. Fetch project to ensure it exists
    project = await project_manager.get_project_by_id(project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

    # 2. Get all versions for project (eager relation handles project eager loading)
    versions = await project_manager.get_versions_for_project(project_id)
    if not versions:
        raise HTTPException(
            status_code=404,
            detail="No versions found for this project."
        )

    # Find the latest completed RAG version to run RAG query on
    latest_rag_version = None
    for v in versions:
        if v.mode == "rag" and v.status == "completed":
            latest_rag_version = v
            break

    if not latest_rag_version:
        logger.warning("No completed RAG version found for project %s", project_id)
        raise HTTPException(
            status_code=404, 
            detail="No completed RAG version found for this project. Ensure you have run an analysis in 'rag' mode."
        )

    # 3. Build version registry table
    registry_lines = [
        f"# Project Meta-Information: {project.name}\n",
        f"This project has {len(versions)} total versions.\n",
        "## Version Registry",
        "| Version Num | Version ID | Status | Mode | Source Type | Source URI | Created At | Completed At |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for v in sorted(versions, key=lambda x: x.version_num):
        created_at_str = v.created_at.strftime("%Y-%m-%d %H:%M:%S") if v.created_at else "N/A"
        completed_at_str = v.completed_at.strftime("%Y-%m-%d %H:%M:%S") if v.completed_at else "N/A"
        registry_lines.append(
            f"| v{v.version_num} | {v.version_id} | {v.status} | {v.mode} | {v.source_type} | {v.source_uri} | {created_at_str} | {completed_at_str} |"
        )
    registry_lines.append("")
    registry_text = "\n".join(registry_lines)

    # 4. Fetch files for all completed versions to calculate diffs
    completed_versions_files = []
    # Sort from oldest to newest
    completed_versions = sorted([v for v in versions if v.status == "completed"], key=lambda x: x.version_num)
    for v in completed_versions:
        files_dict = await _fetch_version_files(project.name, v.version_num)
        if files_dict is not None:
            completed_versions_files.append((v.version_num, files_dict))

    # 5. Compute diffs
    diffs_text = _compute_version_diffs(completed_versions_files)

    # 6. Assemble meta-context
    project_meta_context = f"{registry_text}\n{diffs_text}"

    logger.info("Using latest RAG version %s for project query", latest_rag_version.version_id)
    # Query the RAG index using the discovered version_id
    response = await query_rag_index(
        latest_rag_version.version_id, request, project_meta_context=project_meta_context
    )
    return response


@router.post("/query/version/{version_id}", response_model=QueryResponse)
async def query_version(version_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query a specific RAG-indexed project version.
    """
    # Look up the specific version
    logger.info("Querying version %s: '%s'", version_id, request.question[:100])
    version = await project_manager.get_version(version_id)

    if version is None:
        logger.warning("Version not found: %s", version_id)
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found.")

    if version.mode != "rag":
        logger.warning("Version %s is mode '%s', not 'rag'", version_id, version.mode)
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} was created with mode='{version.mode}'. "
                   f"Querying is only available for mode='rag'.",
        )

    if version.status != "completed":
        logger.warning("Version %s not completed (status=%s)", version_id, version.status)
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} is not completed yet (status: {version.status}). "
                   f"Wait for indexing to finish before querying.",
        )

    # Query the RAG index
    response = await query_rag_index(version_id, request)
    logger.info("Query complete — %d sources, %d tokens", len(response.sources), response.token_count)
    return response


@router.get("/query/project/{project_id}/skeleton")
async def download_project_skeleton(project_id: str):
    """
    Download a high-level project architecture skeleton as a Markdown file.
    Contains directory tree, dependencies, and API symbol surface.
    """
    logger.info("Downloading skeleton for project %s", project_id)
    
    # 1. Fetch the latest completed version (try RAG first, fallback to any completed version)
    version = await project_manager.get_latest_rag_version(project_id)
    if not version:
        versions = await project_manager.get_versions_for_project(project_id)
        for v in versions:
            if v.status == "completed":
                version = v
                break
                
    if not version:
        raise HTTPException(
            status_code=404,
            detail="No completed version found for this project. Please analyze a project version first."
        )

    project_name = version.project.name
    version_num = version.version_num

    # 2. Read context.json from storage
    object_name = f"{project_name}/v{version_num}/output/context.json"
    logger.info("Reading context from storage path: %s", object_name)
    try:
        context_dict = storage_client.client.get_object(storage_client.bucket, object_name)
        data = json.loads(context_dict.read().decode("utf-8"))
        context_dict.close()
        context_dict.release_conn()
        context = ProjectContext(**data)
    except Exception as e:
        logger.error("Failed to load project context for version %s: %s", version.version_id, e)
        raise HTTPException(
            status_code=404,
            detail="Failed to load project context file from storage."
        )

    # 3. Generate skeleton markdown
    content = render_skeleton(context)
    filename = f"{project_name}_v{version_num}_skeleton.md"

    # 4. Return as StreamingResponse
    import io
    bio = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        bio,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/query/project/{project_id}/context")
async def download_query_context(
    project_id: str,
    request: QueryRequest,
):
    """
    Download compiled RAG context (retrieved code chunks relevant to a question) as a Markdown file.
    """
    logger.info("Downloading RAG context for project %s: '%s'", project_id, request.question[:100])
    
    # 1. Fetch the latest completed RAG version
    version = await project_manager.get_latest_rag_version(project_id)
    if not version:
        raise HTTPException(
            status_code=404,
            detail="No completed RAG version found for this project. Context querying is only available for completed RAG versions."
        )

    project_name = version.project.name
    version_num = version.version_num

    # 2. Read context.json from storage
    object_name = f"{project_name}/v{version_num}/output/context.json"
    logger.info("Reading context from storage path: %s", object_name)
    try:
        context_dict = storage_client.client.get_object(storage_client.bucket, object_name)
        data = json.loads(context_dict.read().decode("utf-8"))
        context_dict.close()
        context_dict.release_conn()
        context = ProjectContext(**data)
    except Exception as e:
        logger.error("Failed to load project context for version %s: %s", version.version_id, e)
        raise HTTPException(
            status_code=404,
            detail="Failed to load project context file from storage."
        )

    # 3. Retrieve relevant chunks using RAG logic
    try:
        context_payload, _ = await retrieve_context_payload(version.version_id, request, context)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    content = f"# RAG Context: {request.question}\n\n{context_payload}"
    filename = f"{project_name}_v{version_num}_rag_context.md"

    # 4. Return as StreamingResponse
    import io
    bio = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        bio,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/query/version/{version_id}/skeleton")
async def download_version_skeleton(version_id: str):
    """
    Download a high-level project architecture skeleton for a specific version as a Markdown file.
    Contains directory tree, dependencies, and API symbol surface.
    """
    logger.info("Downloading skeleton for version %s", version_id)
    
    # 1. Fetch the version
    version = await project_manager.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found.")

    if version.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} is not completed (status: {version.status}). Please wait for analysis to complete."
        )

    project_name = version.project.name
    version_num = version.version_num

    # 2. Read context.json from storage
    object_name = f"{project_name}/v{version_num}/output/context.json"
    logger.info("Reading context from storage path: %s", object_name)
    try:
        context_dict = storage_client.client.get_object(storage_client.bucket, object_name)
        data = json.loads(context_dict.read().decode("utf-8"))
        context_dict.close()
        context_dict.release_conn()
        context = ProjectContext(**data)
    except Exception as e:
        logger.error("Failed to load project context for version %s: %s", version.version_id, e)
        raise HTTPException(
            status_code=404,
            detail="Failed to load project context file from storage."
        )

    # 3. Generate skeleton markdown
    content = render_skeleton(context)
    filename = f"{project_name}_v{version_num}_skeleton.md"

    # 4. Return as StreamingResponse
    import io
    bio = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        bio,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/query/version/{version_id}/context")
async def download_version_query_context(
    version_id: str,
    request: QueryRequest,
):
    """
    Download compiled RAG context (retrieved code chunks relevant to a question) for a specific version as a Markdown file.
    """
    logger.info("Downloading RAG context for version %s: '%s'", version_id, request.question[:100])
    
    # 1. Fetch the version
    version = await project_manager.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found.")

    if version.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} is not completed (status: {version.status})."
        )

    if version.mode != "rag":
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} was created with mode='{version.mode}', not 'rag'. Context download is only available for 'rag' versions."
        )

    project_name = version.project.name
    version_num = version.version_num

    # 2. Read context.json from storage
    object_name = f"{project_name}/v{version_num}/output/context.json"
    logger.info("Reading context from storage path: %s", object_name)
    try:
        context_dict = storage_client.client.get_object(storage_client.bucket, object_name)
        data = json.loads(context_dict.read().decode("utf-8"))
        context_dict.close()
        context_dict.release_conn()
        context = ProjectContext(**data)
    except Exception as e:
        logger.error("Failed to load project context for version %s: %s", version.version_id, e)
        raise HTTPException(
            status_code=404,
            detail="Failed to load project context file from storage."
        )

    # 3. Retrieve relevant chunks using RAG logic
    try:
        context_payload, _ = await retrieve_context_payload(version_id, request, context)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    content = f"# RAG Context: {request.question}\n\n{context_payload}"
    filename = f"{project_name}_v{version_num}_rag_context.md"

    # 4. Return as StreamingResponse
    import io
    bio = io.BytesIO(content.encode("utf-8"))
    return StreamingResponse(
        bio,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
