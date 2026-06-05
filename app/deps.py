"""
Shared dependency-injection helpers for FastAPI endpoints.

This module exists to avoid circular imports between
app.main and app.api.* modules.
"""

from __future__ import annotations

from app.services.job_manager import JobManager

# Set by app.main during lifespan startup
_job_manager: JobManager | None = None


def set_job_manager(jm: JobManager) -> None:
    """Called during app startup to inject the JobManager."""
    global _job_manager
    _job_manager = jm


def get_job_manager() -> JobManager:
    """Return the global JobManager instance."""
    if _job_manager is None:
        raise RuntimeError("JobManager not initialized — app not started")
    return _job_manager
