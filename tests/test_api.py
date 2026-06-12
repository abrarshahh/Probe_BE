"""Tests for the FastAPI endpoints."""

import io
import uuid
import zipfile
from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Health check should return 200 with status=healthy."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "probe"


def test_analyze_upload_flow(client: TestClient) -> None:
    """Full lifecycle test using ZIP upload for one_shot mode."""
    # 1. Create a dummy zip file in-memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app/main.py", "print('hello world')\n")
        zf.writestr("requirements.txt", "fastapi>=0.115.0\nuvicorn>=0.30.0\n")
        zf.writestr("package.json", '{"name": "test-pkg", "dependencies": {"express": "^4.18.2"}}\n')
        zf.writestr("README.md", "# Test Project\nThis is a test.")

    zip_bytes = zip_buffer.getvalue()
    project_name = f"test-project-{uuid.uuid4().hex[:8]}"

    # 2. Submit zip to analyze upload endpoint
    response = client.post(
        "/api/v1/projects/upload",
        files={"file": ("test_project.zip", zip_bytes, "application/zip")},
        data={
            "project_name": project_name,
            "mode": "one_shot",
            "output_format": "markdown",
            "options": '{"include_patterns": ["**/*.py", "**/*.json", "requirements.txt", "README.md"]}',
        },
    )
    assert response.status_code == 200
    resp_data = response.json()
    assert "job_id" in resp_data
    job_id = resp_data["job_id"]
    assert resp_data["status"] == "pending"

    # 3. Retrieve job status
    status_response = client.get(f"/api/v1/projects/status/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["version_id"] == job_id
    assert status_data["status"] == "completed"
    assert status_data["progress"]["phase"] in ["building_bundle", "generating_summary", "completed", "building_rag_index"]

    # 4. Download job result
    result_response = client.get(f"/api/v1/versions/{job_id}/download")
    assert result_response.status_code == 200
    result_text = result_response.read().decode("utf-8")
    assert f"# Project Context: {project_name}" in result_text
    assert "Directory Tree" in result_text
    assert "## Dependencies" in result_text
    assert "fastapi" in result_text
    assert "express" in result_text

    # 5. Retrieve project list to find project_id
    projects_response = client.get("/api/v1/projects")
    assert projects_response.status_code == 200
    projects_list = projects_response.json()
    project_id = None
    for p in projects_list:
        if p["project_name"] == project_name:
            project_id = p["project_id"]
            break
    assert project_id is not None

    # 6. Delete version
    delete_version_resp = client.delete(f"/api/v1/versions/{job_id}")
    assert delete_version_resp.status_code == 200
    assert "deleted successfully" in delete_version_resp.json()["message"]

    # 7. Delete project
    delete_proj_resp = client.delete(f"/api/v1/projects/{project_id}")
    assert delete_proj_resp.status_code == 200
    assert "deleted successfully" in delete_proj_resp.json()["message"]

    # 8. Retrieve deleted job (should be 404)
    get_deleted_response = client.get(f"/api/v1/projects/status/{job_id}")
    assert get_deleted_response.status_code == 404


def test_rag_query_and_skeleton_download(client: TestClient) -> None:
    """Test full RAG flow, including skeleton and context downloading."""
    # 1. Create a dummy zip file in-memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app/main.py", "def my_helper():\n    return 'helper value'\n")
        zf.writestr("README.md", "# Test Project\nThis is a RAG test project.")

    zip_bytes = zip_buffer.getvalue()
    project_name = f"test-rag-{uuid.uuid4().hex[:8]}"

    # 2. Submit zip in 'rag' mode
    response = client.post(
        "/api/v1/projects/upload",
        files={"file": ("test_project.zip", zip_bytes, "application/zip")},
        data={
            "project_name": project_name,
            "mode": "rag",
            "output_format": "markdown",
            "options": "{}",
        },
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    # 3. Verify it is completed
    status_response = client.get(f"/api/v1/projects/status/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    # Get project_id
    projects_response = client.get("/api/v1/projects")
    assert projects_response.status_code == 200
    project_id = None
    for p in projects_response.json():
        if p["project_name"] == project_name:
            project_id = p["project_id"]
            break
    assert project_id is not None

    # 4. Download skeleton endpoint (project level)
    skeleton_response = client.get(f"/api/v1/query/project/{project_id}/skeleton")
    assert skeleton_response.status_code == 200
    skeleton_text = skeleton_response.read().decode("utf-8")
    assert "Directory Structure" in skeleton_text
    assert "my_helper" in skeleton_text

    # 5. Download RAG context endpoint (project level)
    context_response = client.post(
        f"/api/v1/query/project/{project_id}/context",
        json={
            "question": "Where is my_helper defined?",
            "max_tokens": 4000,
        }
    )
    assert context_response.status_code == 200
    context_text = context_response.read().decode("utf-8")
    assert "RAG Context: Where is my_helper defined?" in context_text
    assert "my_helper" in context_text

    # 5a. Download skeleton endpoint (version level)
    v_skeleton_response = client.get(f"/api/v1/query/version/{job_id}/skeleton")
    assert v_skeleton_response.status_code == 200
    v_skeleton_text = v_skeleton_response.read().decode("utf-8")
    assert "Directory Structure" in v_skeleton_text
    assert "my_helper" in v_skeleton_text

    # 5b. Download RAG context endpoint (version level)
    v_context_response = client.post(
        f"/api/v1/query/version/{job_id}/context",
        json={
            "question": "Where is my_helper defined?",
            "max_tokens": 4000,
        }
    )
    assert v_context_response.status_code == 200
    v_context_text = v_context_response.read().decode("utf-8")
    assert "RAG Context: Where is my_helper defined?" in v_context_text
    assert "my_helper" in v_context_text

    # Clean up
    client.delete(f"/api/v1/versions/{job_id}")
    client.delete(f"/api/v1/projects/{project_id}")


def test_project_level_meta_queries(client: TestClient) -> None:
    """Test project-level queries that check version counts, registry history, and differences."""
    from pathlib import Path
    import shutil
    import uuid

    # 1. Create local directory and files for Version 1
    tmp_dir = Path("./outputs/temp_test_local").resolve()
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / "app").mkdir(exist_ok=True)
    (tmp_dir / "app" / "main.py").write_text("def my_helper():\n    return 'helper value'\n")
    (tmp_dir / "README.md").write_text("# Test Project\nThis is a RAG test project.")

    project_name = f"test-meta-{uuid.uuid4().hex[:8]}"

    try:
        # Submit analyze request using local source type
        response = client.post(
            "/api/v1/projects/analyze",
            json={
                "project_name": project_name,
                "source": {
                    "type": "local",
                    "url": str(tmp_dir.as_posix()),
                },
                "mode": "rag",
                "output_format": "markdown",
                "options": {},
            },
        )
        assert response.status_code == 200
        v1_job_id = response.json()["job_id"]

        # Verify v1 is completed
        status_response = client.get(f"/api/v1/projects/status/{v1_job_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "completed"

        # Get project_id
        projects_response = client.get("/api/v1/projects")
        assert projects_response.status_code == 200
        project_id = None
        for p in projects_response.json():
            if p["project_name"] == project_name:
                project_id = p["project_id"]
                break
        assert project_id is not None

        # 2. Modify files in the local directory for Version 2 rerun
        # Modify app/main.py
        (tmp_dir / "app" / "main.py").write_text("def my_helper():\n    # updated helper\n    return 'updated value'\n")
        # Add app/helper.py
        (tmp_dir / "app" / "helper.py").write_text("def new_func():\n    pass\n")

        # Trigger rerun (Version 2) - now accepting ONLY project_id, no body!
        rerun_response = client.post(f"/api/v1/projects/{project_id}/rerun")
        assert rerun_response.status_code == 200
        v2_job_id = rerun_response.json()["job_id"]

        # Verify v2 is completed
        status_response = client.get(f"/api/v1/projects/status/{v2_job_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "completed"

        # 3. Query the project about its versions
        query_response = client.post(
            f"/api/v1/query/project/{project_id}",
            json={
                "question": "How many versions are there for this project?",
                "max_tokens": 8000,
            }
        )
        assert query_response.status_code == 200
        answer = query_response.json()["answer"]
        assert any(x in answer.lower() for x in ["2", "two"])

        # 4. Query the project about differences
        diff_query_response = client.post(
            f"/api/v1/query/project/{project_id}",
            json={
                "question": "What is the difference between version 1 and version 2?",
                "max_tokens": 8000,
            }
        )
        assert diff_query_response.status_code == 200
        diff_answer = diff_query_response.json()["answer"]
        assert "helper.py" in diff_answer.lower()
        assert "main.py" in diff_answer.lower()

    finally:
        # Clean up local temp files
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

    # Clean up project/versions from storage/DB
    client.delete(f"/api/v1/versions/{v1_job_id}")
    client.delete(f"/api/v1/versions/{v2_job_id}")
    client.delete(f"/api/v1/projects/{project_id}")
