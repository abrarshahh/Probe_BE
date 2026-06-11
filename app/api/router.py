"""
Main API router — aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.projects import router as projects_router
from app.api.versions import router as versions_router
from app.api.query import router as query_router

api_router = APIRouter()

api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(versions_router, tags=["versions"])
api_router.include_router(query_router, tags=["query"])


@api_router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "probe"}
