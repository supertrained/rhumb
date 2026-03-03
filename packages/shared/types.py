"""Shared Pydantic models used by API and CLI."""

from pydantic import BaseModel


class ServiceRef(BaseModel):
    """Lightweight service identity."""

    slug: str
    name: str


class ScoreRef(BaseModel):
    """Lightweight score identity."""

    service_slug: str
    score: float
    confidence: float
