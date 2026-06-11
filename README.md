# Probe — Codebase Context Engine

A FastAPI backend that ingests software projects and produces LLM-ready context.

## Three Modes

| Mode | Best For | LLM Required? |
|---|---|---|
| **A — One-Shot** | Small/medium projects that fit in a context window | No |
| **B — RAG** | Massive projects (monorepos, millions of lines) | No (embeddings only) |
| **C — Map-Reduce** | Deep understanding via LLM-generated Project Manifesto | Yes (free tier) |

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy and configure environment
cp .env.example .env

# 4. Ensure PostgreSQL and MinIO are running
# Create the 'probe' database in Postgres, and ensure MinIO is accessible on port 9000.

# 5. Run the server
python -m fastapi run .\app\main.py --port 8003
```

## API Usage

### 1. Projects Domain
```bash
# Submit an analysis job
curl -X POST http://localhost:8003/api/v1/projects/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "My Project",
    "source": {"type": "github_url", "url": "https://github.com/user/repo"},
    "mode": "one_shot",
    "output_format": "markdown"
  }'

# List projects (paginated)
curl http://localhost:8000/api/v1/projects?skip=0&limit=10

# Check running job status
curl http://localhost:8000/api/v1/projects/status/{job_id}

# Delete an entire project (Cleans DB, MinIO, and ChromaDB)
curl -X DELETE http://localhost:8000/api/v1/projects/{project_id}
```

### 2. Versions Domain
```bash
# Get all version IDs for a project
curl http://localhost:8000/api/v1/versions/project/{project_id}

# Get info on a specific version
curl http://localhost:8000/api/v1/versions/{version_id}

# Download the analysis result (e.g., markdown bundle)
curl http://localhost:8000/api/v1/versions/{version_id}/download -o result.md

# Delete a specific version
curl -X DELETE http://localhost:8000/api/v1/versions/{version_id}
```

### 3. Query Domain (RAG Mode)
```bash
# Query the entire project (automatically targets the latest RAG version)
curl -X POST http://localhost:8000/api/v1/query/project/{project_id} \
  -H "Content-Type: application/json" \
  -d '{"question": "How does authentication work?"}'

# Query a specific historical version
curl -X POST http://localhost:8000/api/v1/query/version/{version_id} \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is the database config?"}'
```

## Logging

Probe uses a comprehensive, multi-file logging system with color-coded console output.

### Console Color Codes

| Color | Level | Meaning |
|---|---|---|
| 🟢 **Green** | `INFO` | Normal operations (file scans, uploads, progress) |
| 🔵 **Blue** | `IMPORTANT` | Key milestones (server start, pipeline complete, LLM provider selected) |
| 🟡 **Yellow** | `WARNING` | Non-critical issues (skipped files, missing optional config) |
| 🔴 **Red** | `ERROR` / `CRITICAL` | Failures (pipeline crashes, LLM errors, DB connection issues) |

### Log Files

All log files are written to the `logs/` directory:

| File | Contents |
|---|---|
| `logs/app.log` | **All** application logs (DEBUG+). The single source of truth. |
| `logs/error.log` | Errors and critical failures only. Check this first when debugging. |
| `logs/llm.log` | LLM prompts and responses (Gemini, Groq, Ollama). Includes model name, prompt length, and response length. |
| `logs/query.log` | ChromaDB and RAG query logs — embedding lookups, collection operations, retrieval results. |
| `logs/storage.log` | MinIO uploads/downloads and PostgreSQL database operations. |
| `logs/runs/<version_id>.log` | **Per-run isolation.** Each analysis pipeline run gets its own log file, keyed by version ID. Use this to trace exactly what happened during a specific analysis without grepping through `app.log`. |

### Per-Run Log Isolation

Every time an analysis is triggered, the system creates a dedicated log file at `logs/runs/<version_id>.log`. This file captures only the logs from that specific pipeline run, making it easy to debug individual analyses without noise from other concurrent runs.

## Development

```bash
# Run tests
pytest

# Lint
ruff check .

# Type check
mypy app/
```
