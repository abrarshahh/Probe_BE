"""
Job Manager — lifecycle and persistence for analysis jobs.

Uses SQLite for job metadata storage. All operations are async
via aiosqlite.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.models.responses import JobProgress, JobStatusResponse

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    mode TEXT NOT NULL,
    output_format TEXT NOT NULL DEFAULT 'markdown',
    source_type TEXT NOT NULL DEFAULT '',
    source_uri TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    phase TEXT NOT NULL DEFAULT '',
    files_processed INTEGER NOT NULL DEFAULT 0,
    total_files INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    result_path TEXT
);
"""


class JobManager:
    """Manages job records in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        """Create the jobs table if it doesn't exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def create_job(
        self,
        mode: str,
        output_format: str,
        source_type: str = "",
        source_uri: str = "",
    ) -> str:
        """
        Create a new job record and return its ID.

        Args:
            mode: The analysis mode (one_shot, rag, map_reduce).
            output_format: The requested output format.
            source_type: "github_url" or "upload".
            source_uri: The URL or filename.

        Returns:
            The generated job ID.
        """
        job_id = uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (job_id, status, mode, output_format, source_type, source_uri, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, "pending", mode, output_format, source_type, source_uri, now),
            )
            await db.commit()

        return job_id

    async def get_job(self, job_id: str) -> JobStatusResponse | None:
        """Retrieve a job's current status."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = await cursor.fetchone()

        if row is None:
            return None

        progress = JobProgress(
            phase=row["phase"],
            files_processed=row["files_processed"],
            total_files=row["total_files"],
        )

        return JobStatusResponse(
            job_id=row["job_id"],
            status=row["status"],
            mode=row["mode"],
            output_format=row["output_format"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            progress=progress,
            error=row["error"],
        )

    async def update_progress(
        self,
        job_id: str,
        *,
        status: str | None = None,
        phase: str | None = None,
        files_processed: int | None = None,
        total_files: int | None = None,
    ) -> None:
        """Update a job's status and/or progress fields."""
        updates: list[str] = []
        values: list[object] = []

        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if phase is not None:
            updates.append("phase = ?")
            values.append(phase)
        if files_processed is not None:
            updates.append("files_processed = ?")
            values.append(files_processed)
        if total_files is not None:
            updates.append("total_files = ?")
            values.append(total_files)

        if not updates:
            return

        values.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?"

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(sql, values)
            await db.commit()

    async def mark_completed(self, job_id: str, result_path: str | None = None) -> None:
        """Mark a job as completed with the current timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE jobs SET status = 'completed', completed_at = ?, result_path = ? WHERE job_id = ?",
                (now, result_path, job_id),
            )
            await db.commit()

    async def mark_failed(self, job_id: str, error: str) -> None:
        """Mark a job as failed with an error message."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE jobs SET status = 'failed', completed_at = ?, error = ? WHERE job_id = ?",
                (now, error, job_id),
            )
            await db.commit()

    async def get_result_path(self, job_id: str) -> str | None:
        """Get the result file path for a completed job."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT result_path FROM jobs WHERE job_id = ?", (job_id,)
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job record. Returns True if a row was deleted."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            await db.commit()
            return cursor.rowcount > 0
