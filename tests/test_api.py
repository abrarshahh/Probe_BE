"""Tests for the FastAPI endpoints."""

import io
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Health check should return 200 with status=healthy."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "probe"


def test_analyze_upload_flow(client: TestClient) -> None:
    """Full lifecycle test using ZIP upload."""
    # 1. Create a dummy zip file in-memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app/main.py", "print('hello world')\n")
        zf.writestr("requirements.txt", "fastapi>=0.115.0\nuvicorn>=0.30.0\n")
        zf.writestr("package.json", '{"name": "test-pkg", "dependencies": {"express": "^4.18.2"}}\n')
        zf.writestr("README.md", "# Test Project\nThis is a test.")

    zip_bytes = zip_buffer.getvalue()

    # 2. Submit zip to analyze upload endpoint
    response = client.post(
        "/api/v1/analyze/upload",
        files={"file": ("test_project.zip", zip_bytes, "application/zip")},
        data={
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
    status_response = client.get(f"/api/v1/jobs/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["job_id"] == job_id
    assert status_data["status"] == "completed"
    assert status_data["progress"]["phase"] == "running_one_shot"

    # 4. Download job result
    result_response = client.get(f"/api/v1/jobs/{job_id}/result")
    assert result_response.status_code == 200
    result_text = result_response.read().decode("utf-8")
    assert f"# Project Context: project" in result_text
    assert "## Directory Structure" in result_text
    assert "## Dependencies" in result_text
    assert "fastapi" in result_text
    assert "express" in result_text

    # 5. Delete job
    delete_response = client.delete(f"/api/v1/jobs/{job_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == f"Job {job_id} deleted successfully."

    # 6. Retrieve deleted job (should be 404)
    get_deleted_response = client.get(f"/api/v1/jobs/{job_id}")
    assert get_deleted_response.status_code == 404

