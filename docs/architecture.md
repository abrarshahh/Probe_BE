# Probe — Architecture

## Overview

Probe follows a pipeline architecture with three distinct processing modes
that share a common analysis foundation.

## Pipeline Flow

```
Request → Source Resolver → Workspace → Ignore Engine → File Classifier
  → Structure Mapper → Dependency Analyzer → Symbol Extractor → Secret Scanner
  → Mode Dispatch (A / B / C) → Output Formatter → Result
```

## Package Layout

- `app/api/` — FastAPI route handlers
- `app/core/` — Shared pipeline components (scan, classify, extract)
- `app/modes/` — Mode-specific logic (one_shot, rag, map_reduce)
- `app/llm/` — LLM provider abstraction (Gemini, Groq, Ollama)
- `app/output/` — Output format renderers (Markdown, XML, JSON)
- `app/models/` — Pydantic data models (requests, responses, internal)
- `app/services/` — Orchestration and persistence (job manager, pipeline)

## Mode Dispatch

All modes share the same pipeline up to symbol extraction.
After that, each mode branches:

- **Mode A (One-Shot):** Token budget → bundle assembly → output file
- **Mode B (RAG):** Chunking → embedding → ChromaDB → query interface
- **Mode C (Map-Reduce):** LLM map → LLM reduce → manifesto assembly
