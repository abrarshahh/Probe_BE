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
    
    logger.info("Token budget: max=%d, fixed=%d, safety=%d, available=%d", max_tokens, fixed_tokens, safety_margin, available_tokens)
    
    if available_tokens < 0:
        logger.warning("Max tokens is too low to even fit the structural map!")
        available_tokens = 0
        
    file_contents: dict[str, str] = {}
    
    # 2. Rank files intelligently
    # Pre-calculate symbol counts per file to gauge structural importance
    symbols_by_file: dict[str, int] = {}
    for sym in context.symbols:
        symbols_by_file[sym.file_path] = symbols_by_file.get(sym.file_path, 0) + 1
        
    def calculate_score(f) -> float:
        """Calculate a priority score for inclusion (higher is better)."""
        score = 0.0
        
        # Absolute highest priority: Entry points
        if f.path in context.entry_points:
            score += 10000.0
            
        # Category baselines
        if f.category == "source":
            score += 1000.0
        elif f.category == "configuration":
            score += 500.0
        elif f.category == "test":
            score += 200.0
            
        # Structural density: Reward files that export many symbols
        sym_count = symbols_by_file.get(f.path, 0)
        score += (sym_count * 10.0)
        score += (len(f.exports) * 20.0)
        
        # Tie-breaker: Slight penalty for massive files to maximize bundle density
        score -= (f.size_bytes / 100.0)
        
        return score
        
    # Sort descending by score (highest score first)
    sorted_files = sorted(context.files, key=calculate_score, reverse=True)
    
    # 3. Fit files into budget
    current_tokens = 0
    for f in sorted_files:
        try:
            with open(f.absolute_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read()
        except Exception as e:
            logger.warning("Could not read %s: %s", f.path, e)
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
    
    included_count = sum(1 for f in sorted_files if f.status == "included")
    truncated_count = sum(1 for f in sorted_files if f.status == "truncated")
    logger.info(
        "Bundle complete: %d files included, %d truncated, %d tokens used of %d available",
        included_count, truncated_count, current_tokens, available_tokens,
    )
    return file_contents
