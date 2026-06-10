"""
Mode B — RAG Index Builder + Query Engine.

Indexing: Chunk code by symbols, embed with Sentence Transformers, store in ChromaDB.
Querying: Embed question, retrieve relevant chunks, assemble LLM-ready context.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import chromadb

from app.config import settings
from app.core.code_chunker import CodeChunk, chunk_project
from app.core.token_counter import count_tokens, estimate_tokens
from app.models.internal import ProjectContext
from app.models.requests import QueryRequest
from app.models.responses import QueryResponse, QuerySource

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding model (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_embedding_model = None


def _get_embedding_model():
    """Lazily load the SentenceTransformer model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", settings.embedding_model)
        _embedding_model = SentenceTransformer(settings.embedding_model)
        logger.info("Embedding model loaded successfully.")
    return _embedding_model


def _get_chroma_client() -> chromadb.ClientAPI:
    """Get a persistent ChromaDB client."""
    persist_dir = str(settings.chroma_persist_dir)
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=persist_dir)


def _collection_name(job_id: str) -> str:
    """Generate a ChromaDB collection name for a job."""
    # ChromaDB collection names must be 3-63 chars, alphanumeric + underscores
    return f"probe_{job_id}"


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

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
    # 1. Chunk all files
    logger.info("[%s] Chunking project files...", job_id)
    chunks = chunk_project(context.files, context.symbols)
    logger.info("[%s] Generated %d chunks from %d files", job_id, len(chunks), len(context.files))

    if not chunks:
        logger.warning("[%s] No chunks generated — index will be empty", job_id)
        return {"chunk_count": 0, "collection_name": _collection_name(job_id)}

    # 2. Generate embeddings
    logger.info("[%s] Generating embeddings...", job_id)
    model = _get_embedding_model()
    texts = [chunk.text for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=False, batch_size=64)
    embeddings_list = embeddings.tolist()
    logger.info("[%s] Generated %d embeddings", job_id, len(embeddings_list))

    # 3. Create ChromaDB collection
    client = _get_chroma_client()
    collection_name = _collection_name(job_id)

    # Delete existing collection if it exists (re-indexing)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # 4. Upsert code chunks in batches
    batch_size = 500
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_embeddings = embeddings_list[i : i + batch_size]

        ids = [f"chunk_{i + j}" for j in range(len(batch_chunks))]
        documents = [c.text for c in batch_chunks]
        metadatas = [c.metadata for c in batch_chunks]

        collection.add(
            ids=ids,
            embeddings=batch_embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    # 5. Add structural map as special context documents
    structural_docs = _build_structural_documents(context)
    if structural_docs:
        struct_texts = [doc["text"] for doc in structural_docs]
        struct_embeddings = model.encode(struct_texts, show_progress_bar=False).tolist()
        collection.add(
            ids=[doc["id"] for doc in structural_docs],
            embeddings=struct_embeddings,
            documents=struct_texts,
            metadatas=[doc["metadata"] for doc in structural_docs],
        )

    total_chunks = len(chunks) + len(structural_docs)
    logger.info(
        "[%s] RAG index built: %d chunks + %d structural docs in collection '%s'",
        job_id, len(chunks), len(structural_docs), collection_name,
    )

    return {
        "chunk_count": total_chunks,
        "code_chunks": len(chunks),
        "structural_docs": len(structural_docs),
        "collection_name": collection_name,
        "embedding_model": settings.embedding_model,
    }


def _build_structural_documents(context: ProjectContext) -> list[dict]:
    """Build special documents for the structural map."""
    docs = []

    # Directory tree
    if context.directory_tree:
        docs.append({
            "id": "structural_directory_tree",
            "text": f"Project Directory Structure:\n{context.directory_tree}",
            "metadata": {
                "file_path": "<structural_map>",
                "language": "",
                "start_line": "0",
                "end_line": "0",
                "symbol_name": "directory_tree",
                "symbol_kind": "structural",
                "category": "structural",
                "chunk_type": "structural",
            },
        })

    # Entry points
    if context.entry_points:
        ep_text = "Project Entry Points:\n" + "\n".join(
            f"- {ep}" for ep in context.entry_points
        )
        docs.append({
            "id": "structural_entry_points",
            "text": ep_text,
            "metadata": {
                "file_path": "<structural_map>",
                "language": "",
                "start_line": "0",
                "end_line": "0",
                "symbol_name": "entry_points",
                "symbol_kind": "structural",
                "category": "structural",
                "chunk_type": "structural",
            },
        })

    # Dependencies
    if context.dependencies:
        dep_lines = ["Project Dependencies:"]
        for dep in context.dependencies:
            dep_lines.append(f"\n{dep.manifest_file}:")
            if dep.runtime:
                dep_lines.append(f"  Runtime: {', '.join(dep.runtime[:20])}")
            if dep.dev:
                dep_lines.append(f"  Dev: {', '.join(dep.dev[:20])}")
            if dep.framework_guesses:
                dep_lines.append(f"  Frameworks: {', '.join(dep.framework_guesses)}")
        docs.append({
            "id": "structural_dependencies",
            "text": "\n".join(dep_lines),
            "metadata": {
                "file_path": "<structural_map>",
                "language": "",
                "start_line": "0",
                "end_line": "0",
                "symbol_name": "dependencies",
                "symbol_kind": "structural",
                "category": "structural",
                "chunk_type": "structural",
            },
        })

    return docs


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

async def query_rag_index(
    job_id: str,
    request: QueryRequest,
    context: ProjectContext | None = None,
) -> QueryResponse:
    """
    Query a previously built RAG index.

    Embeds the question, retrieves relevant chunks,
    and assembles a context payload.

    Args:
        job_id: The job whose index to query.
        request: The query parameters.
        context: Optional ProjectContext for structural map prepending.

    Returns:
        Assembled context payload with source attributions.
    """
    collection_name = _collection_name(job_id)
    client = _get_chroma_client()

    try:
        collection = client.get_collection(collection_name)
    except Exception as e:
        logger.error("[%s] Could not find RAG collection: %s", job_id, e)
        return QueryResponse(
            context_payload=f"Error: RAG index not found for job {job_id}.",
            sources=[],
            token_count=0,
            structural_map_included=False,
        )

    # 1. Embed the question
    model = _get_embedding_model()
    question_embedding = model.encode([request.question]).tolist()

    # 2. Build metadata filters
    where_filter = _build_where_filter(request.filters)

    # 3. Retrieve top-K chunks
    n_results = 20  # default K

    query_params: dict = {
        "query_embeddings": question_embedding,
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        query_params["where"] = where_filter

    results = collection.query(**query_params)

    if not results["documents"] or not results["documents"][0]:
        return QueryResponse(
            context_payload="No relevant code found for your question.",
            sources=[],
            token_count=0,
            structural_map_included=False,
        )

    # 4. Assemble context
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # Deduplicate overlapping chunks
    seen_keys: set[str] = set()
    unique_chunks: list[tuple[str, dict, float]] = []

    for doc, meta, dist in zip(documents, metadatas, distances):
        # Create a dedup key from file + line range
        key = f"{meta.get('file_path', '')}:{meta.get('start_line', '')}:{meta.get('end_line', '')}"
        if key not in seen_keys:
            seen_keys.add(key)
            unique_chunks.append((doc, meta, dist))

    # 5. Build the context payload
    payload_parts: list[str] = []
    sources: list[QuerySource] = []
    current_tokens = 0

    # Always prepend structural map
    structural_text = _build_structural_preamble(context)
    if structural_text:
        structural_tokens = estimate_tokens(structural_text)
        payload_parts.append(structural_text)
        current_tokens += structural_tokens

    # Add retrieved chunks within token budget
    for doc, meta, dist in unique_chunks:
        chunk_tokens = estimate_tokens(doc)
        if current_tokens + chunk_tokens > request.max_tokens:
            break

        file_path = meta.get("file_path", "unknown")
        start_line = meta.get("start_line", "?")
        end_line = meta.get("end_line", "?")
        language = meta.get("language", "")
        symbol_name = meta.get("symbol_name", "")

        # Format the chunk
        header = f"### {file_path}"
        if symbol_name and symbol_name != "<module>":
            header += f" — {symbol_name}"
        header += f" (lines {start_line}–{end_line})"

        chunk_block = f"{header}\n```{language}\n{doc}\n```\n"
        payload_parts.append(chunk_block)
        current_tokens += chunk_tokens

        # Cosine distance to similarity: similarity = 1 - distance
        relevance = round(max(0.0, 1.0 - dist), 4)
        sources.append(QuerySource(
            file=file_path,
            lines=f"{start_line}-{end_line}",
            relevance=relevance,
        ))

    context_payload = "\n".join(payload_parts)

    # 6. Generate the final answer using the LLM
    from app.core.llm_client import generate_answer

    system_prompt = (
        "You are an expert codebase assistant. The user has asked a question about the project. "
        "You have been provided with specific code chunks retrieved from the project's codebase, "
        "as well as a high-level structural map of the project.\n\n"
        "INSTRUCTIONS:\n"
        "1. Answer the user's question clearly and concisely.\n"
        "2. ONLY use the information provided in the context chunks below. Do NOT hallucinate or guess.\n"
        "3. If the context does not contain enough information to answer the question, explicitly state that you cannot answer based on the provided context.\n"
        "4. Structure your response using markdown. Provide code snippets if they directly help explain your answer, but keep them concise.\n"
        "5. Be direct and beautiful in your formatting."
    )
    
    user_prompt = f"### User Question:\n{request.question}\n\n### Retrieved Context:\n{context_payload}"
    
    answer = await generate_answer(system_prompt, user_prompt)

    return QueryResponse(
        answer=answer,
        context_payload=context_payload,
        sources=sources,
        token_count=current_tokens,
        structural_map_included=bool(structural_text),
    )


def _build_structural_preamble(context: ProjectContext | None) -> str:
    """Build a structural map preamble to prepend to query results."""
    if context is None:
        return ""

    parts = ["## Project Context\n"]

    if context.name:
        parts.append(f"**Project:** {context.name}\n")

    if context.primary_languages:
        parts.append(f"**Languages:** {', '.join(context.primary_languages)}\n")

    if context.directory_tree:
        parts.append("### Directory Structure")
        parts.append(f"```\n{context.directory_tree}\n```\n")

    if context.entry_points:
        parts.append("### Entry Points")
        for ep in context.entry_points:
            parts.append(f"- `{ep}`")
        parts.append("")

    return "\n".join(parts)


def _build_where_filter(filters: dict[str, str]) -> dict | None:
    """Convert user-provided filters to ChromaDB where clause."""
    if not filters:
        return None

    conditions = []
    for key, value in filters.items():
        if key == "language":
            conditions.append({"language": {"$eq": value}})
        elif key == "path_prefix":
            conditions.append({"file_path": {"$contains": value}})
        elif key == "category":
            conditions.append({"category": {"$eq": value}})
        elif key == "symbol_kind":
            conditions.append({"symbol_kind": {"$eq": value}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
