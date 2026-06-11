"""
Project Manager — lifecycle and persistence for projects and their versions.
Uses SQLAlchemy (asyncpg) for metadata and MinIO for file storage.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.models.db import Project, ProjectVersion, utc_now
from app.core.storage import storage_client
from app.modes.rag import delete_rag_index

logger = logging.getLogger(__name__)

class ProjectManager:
    """Manages project and version records in PostgreSQL, and delegates artifact cleanup to MinIO."""

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by its unique name."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project).where(Project.name == name).options(selectinload(Project.versions))
            )
            return result.scalar_one_or_none()

    async def get_project_by_id(self, project_id: str) -> Project | None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project).where(Project.id == project_id).options(selectinload(Project.versions))
            )
            return result.scalar_one_or_none()

    async def list_projects(self, skip: int = 0, limit: int = 100) -> Sequence[Project]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project)
                .options(selectinload(Project.versions))
                .order_by(Project.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            return result.scalars().all()

    async def create_project(self, name: str) -> Project:
        """Create a new project record."""
        logger.info("Creating new project: %s", name)
        async with AsyncSessionLocal() as db:
            project = Project(
                name=name,
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)
            logger.info("Project created with ID: %s", project.id)
            return project

    async def create_version(
        self,
        project_id: str,
        version_num: int,
        mode: str,
        source_type: str,
        source_uri: str,
    ) -> ProjectVersion:
        """Create a new version record for a project."""
        logger.info(
            "Creating version %d for project %s (mode=%s, source_type=%s, source_uri=%s)",
            version_num, project_id, mode, source_type, source_uri
        )
        async with AsyncSessionLocal() as db:
            version = ProjectVersion(
                project_id=project_id,
                version_num=version_num,
                mode=mode,
                source_type=source_type,
                source_uri=source_uri,
                status='pending'
            )
            db.add(version)
            await db.commit()
            await db.refresh(version)
            logger.info("Version created with ID: %s", version.version_id)
            return version

    async def get_version(self, version_id: str) -> ProjectVersion | None:
        """Retrieve a version's current status."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ProjectVersion)
                .where(ProjectVersion.version_id == version_id)
                .options(selectinload(ProjectVersion.project))
            )
            return result.scalar_one_or_none()

    async def get_versions_for_project(self, project_id: str) -> Sequence[ProjectVersion]:
        """Get all versions for a specific project."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project_id)
                .order_by(ProjectVersion.version_num.desc())
            )
            return result.scalars().all()

    async def get_latest_rag_version(self, project_id: str) -> ProjectVersion | None:
        """Get the latest completed RAG version for a project."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ProjectVersion)
                .where(
                    ProjectVersion.project_id == project_id,
                    ProjectVersion.mode == "rag",
                    ProjectVersion.status == "completed"
                )
                .order_by(ProjectVersion.version_num.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def update_progress(
        self,
        version_id: str,
        *,
        status: str | None = None,
        phase: str | None = None,
        files_processed: int | None = None,
        total_files: int | None = None,
    ) -> None:
        """Update a version's status and/or progress fields."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ProjectVersion).where(ProjectVersion.version_id == version_id))
            version = result.scalar_one_or_none()
            if not version:
                return

            if status is not None:
                version.status = status
            if phase is not None:
                version.phase = phase
            if files_processed is not None:
                version.files_processed = files_processed
            if total_files is not None:
                version.total_files = total_files

            await db.commit()

    async def mark_completed(self, version_id: str, metadata: dict[str, Any] | None = None) -> None:
        """Mark a version as completed."""
        logger.info("Marking version %s as completed", version_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ProjectVersion).where(ProjectVersion.version_id == version_id))
            version = result.scalar_one_or_none()
            if version:
                version.status = 'completed'
                if metadata:
                    version.metadata_json = metadata
                version.completed_at = utc_now()
                await db.commit()

    async def mark_failed(self, version_id: str, error: str) -> None:
        """Mark a version as failed with an error message."""
        logger.error("Marking version %s as failed: %s", version_id, error)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ProjectVersion).where(ProjectVersion.version_id == version_id))
            version = result.scalar_one_or_none()
            if version:
                version.status = 'failed'
                version.completed_at = utc_now()
                version.error = error
                await db.commit()

    async def delete_project(self, project_id: str) -> bool:
        """Delete a project from the DB, wipe its MinIO assets, and clear all ChromaDB indices."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Project)
                .where(Project.id == project_id)
                .options(selectinload(Project.versions))
            )
            project = result.scalar_one_or_none()
            if not project:
                return False
                
            project_name = project.name
            version_ids = [v.version_id for v in project.versions]
            
            # Delete from DB (cascade deletes versions)
            await db.delete(project)
            await db.commit()

        # Wipe from MinIO
        storage_client.delete_prefix(f"{project_name}/")
        
        # Delete ChromaDB indices for all versions
        for v_id in version_ids:
            delete_rag_index(v_id)
            
        return True

    async def delete_version(self, version_id: str) -> bool:
        """Delete a specific project version from the DB and wipe its MinIO assets."""
        async with AsyncSessionLocal() as db:
            # We need to load the project as well to get its name for MinIO
            result = await db.execute(
                select(ProjectVersion)
                .where(ProjectVersion.version_id == version_id)
                .options(selectinload(ProjectVersion.project))
            )
            version = result.scalar_one_or_none()
            if not version:
                return False
                
            project_name = version.project.name
            version_num = version.version_num
            
            # Delete from DB
            await db.delete(version)
            await db.commit()

        # Wipe just this version from MinIO
        storage_client.delete_prefix(f"{project_name}/v{version_num}/")
        
        # Delete ChromaDB index
        delete_rag_index(version_id)
        
        return True

# Global manager instance
project_manager = ProjectManager()
