"""
Pipeline Orchestrator — runs the shared analysis pipeline
and dispatches to the selected mode.

This is the main entry point called by the background task.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.modes.one_shot import build_one_shot_bundle
from app.modes.rag import build_rag_index
from app.output.markdown import render_markdown
from app.output.xml_markdown import render_xml_markdown
from app.output.json_output import render_json
from app.core.dependency_analyzer import analyze_dependencies
from app.core.file_classifier import classify_file, classify_skipped_file
from app.core.ignore_engine import IgnoreEngine
from app.core.source_resolver import resolve_source
from app.core.symbol_extractor import extract_symbols
from app.core.test_inferencer import infer_test_mapping
from app.core.structure_mapper import (
    build_file_inventory,
    detect_entry_points,
    generate_directory_tree,
)
from app.core.workspace import WorkspaceManager
from app.models.internal import FileRecord, ProjectContext
from app.models.requests import AnalyzeRequest
from app.services.job_manager import JobManager
from app.llm.base import get_available_provider

logger = logging.getLogger(__name__)


async def run_shared_pipeline(
    request: AnalyzeRequest,
    job_id: str,
    job_manager: JobManager,
) -> tuple[ProjectContext, Path]:
    """
    Execute the shared analysis pipeline (Steps 1-9 from the plan).

    This runs the source resolution, scanning, classification,
    structure mapping, and dependency analysis that all three modes need.

    Args:
        request: The original analysis request.
        job_id: The job identifier.
        job_manager: For updating job progress.

    Returns:
        (ProjectContext, project_root_path) — the aggregated context
        and the path to the project on disk.
    """
    workspace = WorkspaceManager(job_id)

    try:
        # ── Step 1: Update status ────────────────────────────────────────
        await job_manager.update_progress(
            job_id, status="processing", phase="resolving_source"
        )

        # ── Step 2: Create workspace and resolve source ──────────────────
        workspace_path = workspace.create()
        logger.info("[%s] Workspace created: %s", job_id, workspace_path)

        upload_path_str = getattr(request, "_upload_path", None)
        upload_path = Path(upload_path_str) if upload_path_str else None

        project_root = await resolve_source(
            source_type=request.source.type,
            workspace_path=workspace_path,
            url=request.source.url,
            branch=request.source.branch,
            github_token=request.source.github_token,
            upload_path=upload_path,
        )
        logger.info("[%s] Source resolved: %s", job_id, project_root)

        # ── Step 3: Scan files with ignore engine ────────────────────────
        await job_manager.update_progress(job_id, phase="scanning")

        ignore_engine = IgnoreEngine(
            project_root=project_root,
            include_patterns=request.options.include_patterns or None,
            exclude_patterns=request.options.exclude_patterns or None,
            max_file_size=settings.max_file_size_mb * 1024 * 1024,
        )

        included_paths, skipped_entries = ignore_engine.scan_directory()
        logger.info(
            "[%s] Scan complete: %d included, %d skipped",
            job_id, len(included_paths), len(skipped_entries),
        )

        await job_manager.update_progress(
            job_id,
            total_files=len(included_paths) + len(skipped_entries),
            files_processed=0,
        )

        # ── Step 4: Classify files ───────────────────────────────────────
        await job_manager.update_progress(job_id, phase="classifying")

        included_files: list[FileRecord] = []
        for i, file_path in enumerate(included_paths):
            record = classify_file(file_path, project_root)
            included_files.append(record)

            # Update progress every 50 files
            if (i + 1) % 50 == 0:
                await job_manager.update_progress(
                    job_id, files_processed=i + 1
                )

        skipped_files: list[FileRecord] = [
            classify_skipped_file(path, project_root, reason)
            for path, reason in skipped_entries
        ]

        await job_manager.update_progress(
            job_id, files_processed=len(included_paths)
        )

        logger.info(
            "[%s] Classification complete: %d files classified",
            job_id, len(included_files),
        )

        # ── Step 5: Map structure ────────────────────────────────────────
        await job_manager.update_progress(job_id, phase="mapping_structure")

        all_files = included_files + skipped_files
        directory_tree = generate_directory_tree(project_root, all_files)
        entry_points = detect_entry_points(included_files)
        file_inventory = build_file_inventory(included_files)

        logger.info(
            "[%s] Structure mapped: %d entry points found",
            job_id, len(entry_points),
        )

        # ── Step 6: Analyze dependencies ─────────────────────────────────
        await job_manager.update_progress(job_id, phase="analyzing_dependencies")

        dependencies = analyze_dependencies(project_root)
        logger.info(
            "[%s] Dependencies analyzed: %d manifests found",
            job_id, len(dependencies),
        )

        # ── Step 7: Detect primary languages ─────────────────────────────
        language_counts: dict[str, int] = {}
        for f in included_files:
            if f.language and f.category == "source":
                language_counts[f.language] = language_counts.get(f.language, 0) + 1

        primary_languages = sorted(
            language_counts, key=lambda l: language_counts[l], reverse=True
        )[:5]

        # ── Step 8: Extract symbols ──────────────────────────────────────
        await job_manager.update_progress(job_id, phase="extracting_symbols")

        all_symbols = []
        for f in included_files:
            result = extract_symbols(Path(f.absolute_path), f.language)
            all_symbols.extend(result.symbols)
            f.imports = result.imports
            f.exports = result.exports

        logger.info(
            "[%s] Symbol extraction complete: %d symbols from %d files",
            job_id, len(all_symbols), len(included_files),
        )

        # ── Step 9: Test-to-source inference ──────────────────────────────
        await job_manager.update_progress(job_id, phase="inferring_test_mapping")

        test_mapping = infer_test_mapping(included_files)

        # Attach test targets to the FileRecords
        for test_path, source_paths in test_mapping.items():
            for f in included_files:
                if f.path == test_path:
                    f.test_targets = source_paths
                    break

        logger.info(
            "[%s] Test inference complete: %d test files mapped",
            job_id, len(test_mapping),
        )

        # ── Step 10: Extract project name ────────────────────────────────
        project_name = project_root.name
        source_uri = request.source.url or ""

        # ── Assemble context ─────────────────────────────────────────────
        context = ProjectContext(
            name=project_name,
            source_type=request.source.type,
            source_uri=source_uri,
            branch=request.source.branch,
            root_path=str(project_root),
            primary_languages=primary_languages,
            directory_tree=directory_tree,
            files=included_files,
            symbols=all_symbols,
            dependencies=dependencies,
            entry_points=entry_points,
            skipped_files=skipped_files,
            test_mapping=test_mapping,
        )

        logger.info(
            "[%s] Shared pipeline complete: %d files, %d langs, %d deps",
            job_id,
            len(included_files),
            len(primary_languages),
            len(dependencies),
        )

        return context, project_root

    except Exception:
        # Don't cleanup workspace on failure — leave for debugging
        logger.exception("[%s] Pipeline failed", job_id)
        raise


async def run_pipeline(
    request: AnalyzeRequest,
    job_id: str,
    job_manager: JobManager,
) -> None:
    """
    Execute the full analysis pipeline for a job.

    Runs the shared pipeline, then dispatches to the selected mode.

    Args:
        request: The original analysis request.
        job_id: The job identifier.
        job_manager: For updating job progress.
    """
    try:
        # Run shared pipeline
        context, project_root = await run_shared_pipeline(
            request, job_id, job_manager
        )

        # ── Mode dispatch ────────────────────────────────────────────────
        await job_manager.update_progress(job_id, phase=f"running_{request.mode}")

        output_dir = settings.output_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        if request.mode == "one_shot":
            # Mode A — one_shot (Milestone 2 integration)
            await job_manager.update_progress(job_id, phase="building_bundle")
            
            # 1. Build the bundle (handles token budget & file reading)
            file_contents = await build_one_shot_bundle(context, request.options.max_tokens)
            
            # 2. Assemble prompt for LLM
            # We create a simple markdown representation to send to the Simple LLM
            # It just needs to read the code to summarize it.
            bundle_prompt = render_markdown(context, "Please summarize this codebase.", file_contents)
            
            await job_manager.update_progress(job_id, phase="generating_summary")
            provider = await get_available_provider(settings.llm_providers, tier="simple")
            logger.info("[%s] Using Simple LLM provider: %s", job_id, provider.name)
            
            # 3. Use the LLM to generate the context summary
            summary = await provider.generate(bundle_prompt, max_tokens=8000)
            
            # 4. Format final output
            if request.output_format == "json":
                final_output = render_json(context, summary, file_contents)
            elif request.output_format == "xml_markdown":
                final_output = render_xml_markdown(context, summary, file_contents)
            else:
                final_output = render_markdown(context, summary, file_contents)
            
            result_path = output_dir / f"context.{_format_extension(request.output_format)}"
            result_path.write_text(final_output, encoding="utf-8")
            
            await job_manager.mark_completed(job_id, result_path=str(result_path))

        elif request.mode == "rag":
            # Mode B — RAG index builder (Milestone 4)
            await job_manager.update_progress(job_id, phase="building_rag_index")

            import json as _json
            index_meta = await build_rag_index(context, project_root, job_id)

            # Save index metadata
            meta_path = output_dir / "index_meta.json"
            meta_path.write_text(_json.dumps(index_meta, indent=2), encoding="utf-8")

            logger.info(
                "[%s] RAG index complete: %d chunks in collection '%s'",
                job_id, index_meta.get("chunk_count", 0), index_meta.get("collection_name", ""),
            )

            await job_manager.mark_completed(job_id, result_path=str(meta_path))

        elif request.mode == "map_reduce":
            # TODO: Mode C — Map-Reduce summarizer (Milestone 5)
            await job_manager.mark_completed(job_id)

        else:
            await job_manager.mark_failed(job_id, f"Unknown mode: {request.mode}")

        logger.info("[%s] Pipeline completed successfully", job_id)

    except Exception as e:
        logger.exception("[%s] Pipeline failed", job_id)
        await job_manager.mark_failed(job_id, str(e))


def _format_extension(output_format: str) -> str:
    """Map output format name to file extension."""
    return {
        "markdown": "md",
        "xml_markdown": "xml",
        "json": "json",
    }.get(output_format, "md")


def _build_placeholder_output(context: ProjectContext, output_format: str) -> str:
    """
    Build a basic placeholder output until mode-specific builders are implemented.

    This gives a useful result even in Milestone 1 — it shows the
    structural map and file inventory.
    """
    lines: list[str] = []
    lines.append(f"# Project Context: {context.name}\n")
    lines.append("## Project Summary\n")
    lines.append(f"- **Source:** {context.source_type} — {context.source_uri}")
    lines.append(f"- **Languages:** {', '.join(context.primary_languages) or 'Unknown'}")
    lines.append(f"- **Total Files:** {len(context.files) + len(context.skipped_files)}")
    lines.append(f"- **Included Files:** {len(context.files)}")
    lines.append(f"- **Skipped Files:** {len(context.skipped_files)}")
    lines.append("")

    lines.append("## Directory Structure\n")
    lines.append("```")
    lines.append(context.directory_tree)
    lines.append("```\n")

    if context.entry_points:
        lines.append("## Entry Points\n")
        for ep in context.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("")

    if context.dependencies:
        lines.append("## Dependencies\n")
        for dep in context.dependencies:
            lines.append(f"### {dep.manifest_file}\n")
            if dep.framework_guesses:
                lines.append(f"**Frameworks:** {', '.join(dep.framework_guesses)}\n")
            if dep.runtime:
                lines.append("**Runtime:**")
                for d in dep.runtime[:30]:
                    lines.append(f"- {d}")
                if len(dep.runtime) > 30:
                    lines.append(f"- ... and {len(dep.runtime) - 30} more")
                lines.append("")
            if dep.dev:
                lines.append("**Dev:**")
                for d in dep.dev[:20]:
                    lines.append(f"- {d}")
                if len(dep.dev) > 20:
                    lines.append(f"- ... and {len(dep.dev) - 20} more")
                lines.append("")
            if dep.scripts:
                lines.append("**Scripts:**")
                for name, cmd in dep.scripts.items():
                    lines.append(f"- `{name}`: `{cmd}`")
                lines.append("")

    if context.skipped_files:
        lines.append("## Skipped Files\n")
        lines.append("| File | Reason |")
        lines.append("|---|---|")
        for sf in context.skipped_files[:50]:
            lines.append(f"| {sf.path} | {sf.skip_reason} |")
        if len(context.skipped_files) > 50:
            lines.append(f"| ... | {len(context.skipped_files) - 50} more skipped |")
        lines.append("")

    # File inventory by category
    from app.core.structure_mapper import build_file_inventory
    inventory = build_file_inventory(context.files)
    lines.append("## File Inventory\n")
    for category, file_list in sorted(inventory.items()):
        lines.append(f"### {category.replace('_', ' ').title()} ({len(file_list)} files)\n")
        for fp in file_list[:30]:
            lines.append(f"- `{fp}`")
        if len(file_list) > 30:
            lines.append(f"- ... and {len(file_list) - 30} more")
        lines.append("")

    return "\n".join(lines)
