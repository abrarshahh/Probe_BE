# Probe — API Reference

## Base URL

```
http://localhost:8000/api/v1
```

## Endpoints

### `GET /health`

Health check. Returns `{"status": "healthy", "service": "probe"}`.

### `POST /analyze`

Submit a new analysis job.

**Request Body:**

```json
{
  "source": {
    "type": "github_url",
    "url": "https://github.com/user/repo",
    "branch": "main",
    "github_token": null
  },
  "mode": "one_shot | rag | map_reduce",
  "output_format": "markdown | xml_markdown | json",
  "options": {
    "max_tokens": 128000,
    "include_patterns": [],
    "exclude_patterns": [],
    "redact_secrets": true
  }
}
```

**Response:** `{"job_id": "abc123", "status": "pending"}`

### `POST /analyze/upload`

Submit via file upload (multipart/form-data).

### `GET /jobs/{job_id}`

Check job status and progress.

### `GET /jobs/{job_id}/result`

Download the generated output artifact.

### `DELETE /jobs/{job_id}`

Delete a job and its artifacts.

### `POST /jobs/{job_id}/query`

Query a RAG-indexed project (Mode B only).

**Request Body:**

```json
{
  "question": "How does authentication work?",
  "max_tokens": 8000,
  "filters": {"language": "python"}
}
```
