"""Shared fixtures for API tests."""

from fastapi.testclient import TestClient

from app import app


import pytest


@pytest.fixture
def client() -> TestClient:
    """Create an in-process FastAPI test client."""
    return TestClient(app)
