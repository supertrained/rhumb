"""Schema references for shared use.

Canonical public score read surface: `scores`.
Legacy engine/SQLAlchemy lineage still includes `an_scores` + `dimension_scores`.
"""

CANONICAL_PUBLIC_SCORE_SURFACE = "scores"

PUBLIC_READ_TABLES = [
    "services",
    "scores",
    "failure_modes",
    "agents",
    "agent_usage_events",
    "query_logs",
]

LEGACY_ENGINE_TABLES = [
    "dimension_scores",
    "an_scores",
    "probe_results",
    "schema_snapshots",
]

CORE_TABLES = PUBLIC_READ_TABLES + LEGACY_ENGINE_TABLES
