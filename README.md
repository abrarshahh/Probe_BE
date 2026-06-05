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

# 4. Run the server
uvicorn app.main:app --reload
```

## API Usage

```bash
# Submit an analysis job
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "source": {"type": "github_url", "url": "https://github.com/user/repo"},
    "mode": "one_shot",
    "output_format": "markdown"
  }'

# Check job status
curl http://localhost:8000/api/v1/jobs/{job_id}

# Download result
curl http://localhost:8000/api/v1/jobs/{job_id}/result

# Query a RAG-indexed project (Mode B only)
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How does authentication work?"}'
```

## Development

```bash
# Run tests
pytest

# Lint
ruff check .

# Type check
mypy app/
```
