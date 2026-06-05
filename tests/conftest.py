"""
Pytest configuration and shared fixtures.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


from typing import Generator

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """FastAPI test client."""
    with TestClient(app) as c:
        yield c
