"""Supabase credential-role helpers for structural data separation.

This module centralizes which credential surface should be used for which
Supabase interaction so score-truth reads can move off the broad app/control
plane credential without forcing every route to hand-roll header logic.
"""

from __future__ import annotations

from config import settings

_SCORE_TRUTH_TABLES = frozenset({"scores", "score_audit_chain"})


def _first_path_segment(target: str) -> str:
    stripped = target.lstrip("/")
    if stripped.startswith("rest/v1/"):
        stripped = stripped.removeprefix("rest/v1/")
    return stripped.split("?", 1)[0].split("/", 1)[0]


def is_score_truth_target(target: str) -> bool:
    """Return True when a table/path targets protected score truth."""
    return _first_path_segment(target) in _SCORE_TRUTH_TABLES


def build_supabase_headers(api_key: str) -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
    }


def get_app_supabase_headers() -> dict[str, str]:
    """Headers for the general Resolve/runtime control plane."""
    return build_supabase_headers(settings.supabase_service_role_key)


def get_score_reader_supabase_headers() -> dict[str, str]:
    """Headers for score-truth read paths.

    Falls back to the broad service-role credential until a dedicated
    score-reader key is provisioned in each environment.
    """
    return build_supabase_headers(
        settings.supabase_score_reader_key or settings.supabase_service_role_key
    )


def get_score_publisher_supabase_headers() -> dict[str, str]:
    """Headers for the score publisher/write surface.

    Falls back to the broad service-role credential until a dedicated
    score-publisher key is provisioned in each environment.
    """
    return build_supabase_headers(
        settings.supabase_score_publisher_key or settings.supabase_service_role_key
    )
