"""
Comprehensive logging configuration for Probe Backend.

Log Files:
    logs/app.log       — All logs (DEBUG+)
    logs/error.log     — Errors only (ERROR+)
    logs/llm.log       — LLM input/output (prompts and responses)
    logs/query.log     — ChromaDB / RAG query related logs
    logs/storage.log   — MinIO and PostgreSQL related logs
    logs/runs/<id>.log — Per-analysis-run logs, keyed by version_id

Console Output (Color Coded):
    GREEN  — INFO (normal operations)
    YELLOW — WARNING
    RED    — ERROR / CRITICAL
    BLUE   — Important milestones (custom IMPORTANT level)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Custom IMPORTANT log level (between INFO and WARNING)
# ---------------------------------------------------------------------------
IMPORTANT = 25
logging.addLevelName(IMPORTANT, "IMPORTANT")


def important(self: logging.Logger, message: str, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
    """Log an IMPORTANT-level message (blue in console)."""
    if self.isEnabledFor(IMPORTANT):
        self._log(IMPORTANT, message, args, **kwargs)


logging.Logger.important = important  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------
class _AnsiColors:
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    BOLD_RED = "\033[1;31m"


# ---------------------------------------------------------------------------
# Color formatter for console
# ---------------------------------------------------------------------------
class ColorFormatter(logging.Formatter):
    """Formatter that adds ANSI color codes based on log level."""

    LEVEL_COLORS = {
        logging.DEBUG: _AnsiColors.GREEN,
        logging.INFO: _AnsiColors.GREEN,
        logging.WARNING: _AnsiColors.YELLOW,
        logging.ERROR: _AnsiColors.RED,
        logging.CRITICAL: _AnsiColors.BOLD_RED,
        IMPORTANT: _AnsiColors.BLUE,
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D102
        color = self.LEVEL_COLORS.get(record.levelno, _AnsiColors.RESET)
        # Inject the run_id tag if present
        run_id = getattr(record, "run_id", None)
        run_tag = f"[{run_id[:12]}] " if run_id else ""
        record.run_tag = run_tag

        formatted = super().format(record)
        return f"{color}{formatted}{_AnsiColors.RESET}"


# ---------------------------------------------------------------------------
# Plain formatter for file handlers
# ---------------------------------------------------------------------------
class FileFormatter(logging.Formatter):
    """Formatter for log files — no ANSI codes, includes run_id tag."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D102
        run_id = getattr(record, "run_id", None)
        run_tag = f"[{run_id[:12]}] " if run_id else ""
        record.run_tag = run_tag
        return super().format(record)


# ---------------------------------------------------------------------------
# Per-run file handler cache (one .log file per version_id)
# ---------------------------------------------------------------------------
_run_handlers: dict[str, logging.FileHandler] = {}


def get_run_logger(run_id: str) -> logging.Logger:
    """
    Get a logger that writes to both the normal handlers AND a
    per-run log file at ``logs/runs/<run_id>.log``.
    """
    logger_name = f"app.run.{run_id[:12]}"
    run_logger = logging.getLogger(logger_name)

    if run_id not in _run_handlers:
        run_dir = Path("logs/runs")
        run_dir.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(run_dir / f"{run_id}.log", encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(FileFormatter(
            "%(asctime)s | %(levelname)-9s | %(name)s | %(message)s"
        ))
        _run_handlers[run_id] = handler
        run_logger.addHandler(handler)

    return run_logger


def cleanup_run_logger(run_id: str) -> None:
    """Remove and close the per-run handler after a pipeline run finishes."""
    handler = _run_handlers.pop(run_id, None)
    if handler:
        handler.close()
        logger_name = f"app.run.{run_id[:12]}"
        run_logger = logging.getLogger(logger_name)
        run_logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# Module-level filter classes
# ---------------------------------------------------------------------------
class _NamePrefixFilter(logging.Filter):
    """Only pass records whose logger name starts with one of the prefixes."""

    def __init__(self, prefixes: list[str]) -> None:
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D102
        return any(record.name.startswith(p) for p in self.prefixes)


# ---------------------------------------------------------------------------
# Main setup (call once from main.py)
# ---------------------------------------------------------------------------
def setup_logging(*, debug: bool = False) -> None:
    """Configure the entire application logging stack."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Clear any pre-existing handlers (e.g. from basicConfig)
    root.handlers.clear()

    fmt_str = "%(asctime)s | %(levelname)-9s | %(name)s | %(run_tag)s%(message)s"

    # ── 1. Console handler (colored) ──────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(ColorFormatter(fmt_str))
    root.addHandler(console)

    # ── 2. logs/app.log — everything ──────────────────────────────────────
    app_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(FileFormatter(fmt_str))
    root.addHandler(app_handler)

    # ── 3. logs/error.log — ERROR and above ───────────────────────────────
    err_handler = logging.FileHandler(log_dir / "error.log", encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(FileFormatter(fmt_str))
    root.addHandler(err_handler)

    # ── 4. logs/llm.log — LLM-related loggers ────────────────────────────
    llm_handler = logging.FileHandler(log_dir / "llm.log", encoding="utf-8")
    llm_handler.setLevel(logging.DEBUG)
    llm_handler.setFormatter(FileFormatter(fmt_str))
    llm_handler.addFilter(_NamePrefixFilter([
        "app.llm",
        "app.core.llm_client",
    ]))
    root.addHandler(llm_handler)

    # ── 5. logs/query.log — ChromaDB / RAG query logs ─────────────────────
    query_handler = logging.FileHandler(log_dir / "query.log", encoding="utf-8")
    query_handler.setLevel(logging.DEBUG)
    query_handler.setFormatter(FileFormatter(fmt_str))
    query_handler.addFilter(_NamePrefixFilter([
        "app.modes.rag",
        "app.api.query",
        "chromadb",
    ]))
    root.addHandler(query_handler)

    # ── 6. logs/storage.log — MinIO and DB logs ───────────────────────────
    storage_handler = logging.FileHandler(log_dir / "storage.log", encoding="utf-8")
    storage_handler.setLevel(logging.DEBUG)
    storage_handler.setFormatter(FileFormatter(fmt_str))
    storage_handler.addFilter(_NamePrefixFilter([
        "app.core.storage",
        "app.db",
        "app.services.project_manager",
        "sqlalchemy",
        "minio",
    ]))
    root.addHandler(storage_handler)

    # ── Quieten noisy third-party loggers ─────────────────────────────────
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
