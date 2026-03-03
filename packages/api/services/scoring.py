"""Scoring service placeholders for WU 1.1."""

from dataclasses import dataclass


@dataclass(slots=True)
class ScoreContext:
    """Inputs required for AN score computation."""

    service_slug: str


def calculate_score(context: ScoreContext) -> dict:
    """Placeholder composite score function.

    The full scoring implementation lands in WU 1.1.
    """

    return {
        "service": context.service_slug,
        "score": None,
        "confidence": None,
        "tier": "unscored",
        "explanation": "Scoring engine not implemented yet.",
    }
