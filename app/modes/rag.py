"""
Mode B — RAG Index Builder + Query Engine.

Indexing: Chunk code by symbols, embed with Sentence Transformers, store in ChromaDB.
Querying: Embed question, retrieve relevant chunks, assemble LLM-ready context.
"""

from __future__ import annotations

from pathlib import Path

from app.models.internal import ProjectContext
from app.models.requests import QueryRequest
from app.models.responses import QueryResponse


async def build_rag_index(
    context: ProjectContext,
    project_root: Path,
    job_id: str,
) -> dict:
    """
    Build a RAG index for the analyzed project.

    Chunks code into semantic units, generates embeddings,
    and stores everything in ChromaDB.

    Args:
        context: Aggregated project context from the shared pipeline.
        project_root: Path to the project files.
        job_id: Unique job identifier for the ChromaDB collection.

    Returns:
        Index metadata (chunk count, collection name, etc.).
    """
    # TODO: Implement chunking, embedding, ChromaDB storage
    raise NotImplementedError


async def query_rag_index(
    job_id: str,
    request: QueryRequest,
) -> QueryResponse:
    """
    Query a previously built RAG index.

    Embeds the question, retrieves relevant chunks,
    and assembles a context payload.

    Args:
        job_id: The job whose index to query.
        request: The query parameters.

    Returns:
        Assembled context payload with source attributions.
    """
    # TODO: Implement query, retrieval, context assembly
    raise NotImplementedError
