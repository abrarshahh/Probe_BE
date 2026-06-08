"""
Mode A — One-Shot Context Bundle Builder.

Takes the shared pipeline output and assembles a single LLM-ready file.
Handles token budgeting, file importance ranking, and truncation.

No LLM calls — purely deterministic.
"""

from __future__ import annotations

import logging
from app.models.internal import ProjectContext
from app.core.token_counter import count_tokens

logger = logging.getLogger(__name__)

async def build_one_shot_bundle(
    context: ProjectContext,
    max_tokens: int,
) -> dict[str, str]:
    """
    Build a one-shot context bundle from the analyzed project.
    Applies token budgeting and ranks files by importance.

    Args:
        context: Aggregated project context from the shared pipeline.
        max_tokens: Maximum token budget for the output.

    Returns:
        Mapping of relative path -> file content.
    """
    # 1. Estimate fixed tokens for structural map and summary prompt
    fixed_text = f"{context.directory_tree}\n" + "\n".join(context.entry_points)
    fixed_tokens = count_tokens(fixed_text)
    
    # Reserve tokens for LLM summary generation and basic structure
    safety_margin = 2000 
    available_tokens = max_tokens - fixed_tokens - safety_margin
    
    if available_tokens < 0:
        logger.warning("Max tokens is too low to even fit the structural map!")
        available_tokens = 0
        
    file_contents: dict[str, str] = {}
    
    # 2. Rank files
    # Priority: Entry points > Small files > Others
    # For now, simply sort by whether it's an entry point, then by size
    def get_priority(file_path: str) -> int:
        if file_path in context.entry_points:
            return 0
        return 1
        
    sorted_files = sorted(context.files, key=lambda f: (get_priority(f.path), f.size_bytes))
    
    # 3. Fit files into budget
    current_tokens = 0
    for f in sorted_files:
        try:
            with open(f.absolute_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()
        except Exception as e:
            logger.warning(f"Could not read {f.path}: {e}")
            f.status = "skipped"
            f.skip_reason = f"Read error: {e}"
            continue
            
        file_tokens = count_tokens(content)
        
        if current_tokens + file_tokens <= available_tokens:
            file_contents[f.path] = content
            current_tokens += file_tokens
            f.status = "included"
        else:
            # File doesn't fit completely
            f.status = "truncated"
            file_contents[f.path] = f"# TRUNCATED - Exceeds Token Budget"
            
    return file_contents
