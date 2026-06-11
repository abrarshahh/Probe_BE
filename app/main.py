"""
FastAPI application factory and lifespan management.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.db.database import init_db
from app.core.storage import storage_client

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown logic."""
    # Startup
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", settings.output_dir.resolve())

    # Initialize PostgreSQL Database
    await init_db()
    logger.info("Database initialized")
    
    # Initialize Storage Client (ensures bucket)
    storage_client.initialize()
    logger.info("MinIO storage initialized, bucket: %s", storage_client.bucket)

    logger.info("Probe backend started on %s:%s", settings.host, settings.port)

    yield

    # Shutdown
    logger.info("Probe backend shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Probe — Codebase Context Engine",
        description="Ingest software projects and produce LLM-ready context.",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api/v1")

    return application


app = create_app()
