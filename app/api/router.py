"""
Main API router — aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.analyze import router as analyze_router
from app.api.jobs import router as jobs_router
from app.api.query import router as query_router

api_router = APIRouter()

api_router.include_router(analyze_router, tags=["analyze"])
api_router.include_router(jobs_router, tags=["jobs"])
api_router.include_router(query_router, tags=["query"])


@api_router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "probe"}
