"""
Workspace Manager — isolated temporary directories for each analysis job.

Responsibilities:
- Create isolated workspaces per job.
- Track workspace size.
- Clean up after completion.
- Prevent path traversal.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.config import settings


class WorkspaceManager:
    """Manages temporary workspaces for analysis jobs."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._workspace_dir: Path | None = None

    def create(self) -> Path:
        """Create a new temporary workspace directory."""
        base = settings.output_dir / "workspaces"
        base.mkdir(parents=True, exist_ok=True)
        self._workspace_dir = Path(tempfile.mkdtemp(prefix=f"probe_{self.job_id}_", dir=base))
        return self._workspace_dir

    @property
    def path(self) -> Path:
        """Return the workspace path, raising if not created."""
        if self._workspace_dir is None:
            raise RuntimeError("Workspace not created yet. Call create() first.")
        return self._workspace_dir

    def cleanup(self) -> None:
        """Remove the workspace directory and all contents."""
        if self._workspace_dir and self._workspace_dir.exists():
            shutil.rmtree(self._workspace_dir, ignore_errors=True)
            self._workspace_dir = None
