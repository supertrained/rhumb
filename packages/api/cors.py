"""Shared CORS allowlist and helpers for browser-facing API responses."""

from __future__ import annotations

ALLOWED_CORS_ORIGINS = [
    "https://rhumb.dev",
    "https://www.rhumb.dev",
    "https://rhumb-orcin.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
]


def build_cors_headers(origin: str | None) -> dict[str, str]:
    """Return CORS headers for an explicitly allowlisted origin."""
    if origin not in ALLOWED_CORS_ORIGINS:
        return {}

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }
