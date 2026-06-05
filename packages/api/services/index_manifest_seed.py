"""Deterministic hosted Index manifest seed payloads.

This module renders the PP-2 command manifest fixtures into the durable
``index_command_manifests`` table shape.  The generated SQL is intentionally a
fixture seed, not evidence of production execution: manifest/evidence digests
and public claim boundaries are preserved exactly, and evidence columns are only
filled when an Index evidence packet fixture already exists.
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from schemas.capability_manifest import command_manifest_fixtures
from schemas.index_evidence import route_fixture_for

INDEX_COMMAND_MANIFEST_SEED_MIGRATION = "0166_index_command_manifest_seed.sql"

_SEED_COLUMNS = (
    "route_id",
    "manifest_id",
    "manifest_version",
    "manifest_digest",
    "service_id",
    "provider_id",
    "capability_id",
    "substrate",
    "provenance_origin",
    "source_risk",
    "side_effect_class",
    "promotion_state",
    "review_status",
    "evidence_packet_id",
    "evidence_packet_digest",
    "evidence_expires_at",
    "public_claim_boundary",
    "manifest_json",
    "evidence_packet_json",
    "owner",
    "reviewer",
    "expires_at",
)

_JSONB_COLUMNS = frozenset({"manifest_json", "evidence_packet_json"})
_TIMESTAMPTZ_COLUMNS = frozenset({"evidence_expires_at", "expires_at"})


def _evidence_packet_for_manifest(manifest: dict[str, Any]) -> dict[str, Any] | None:
    fixture = route_fixture_for(str(manifest.get("capability_id") or ""), str(manifest.get("provider_id") or ""))
    if not isinstance(fixture, dict):
        return None

    evidence_packet = fixture.get("evidence_packet")
    if not isinstance(evidence_packet, dict):
        return None

    if evidence_packet.get("route_id") != manifest.get("route_id"):
        return None

    return deepcopy(evidence_packet)


def index_command_manifest_seed_rows() -> list[dict[str, Any]]:
    """Return deterministic rows for seeding hosted Index manifest storage."""

    rows: list[dict[str, Any]] = []
    for manifest in command_manifest_fixtures():
        manifest_json = deepcopy(manifest)
        evidence_packet = _evidence_packet_for_manifest(manifest_json)
        rows.append(
            {
                "route_id": manifest_json["route_id"],
                "manifest_id": manifest_json["manifest_id"],
                "manifest_version": manifest_json["manifest_version"],
                "manifest_digest": manifest_json["manifest_digest"],
                "service_id": manifest_json["service_id"],
                "provider_id": manifest_json["provider_id"],
                "capability_id": manifest_json["capability_id"],
                "substrate": manifest_json["substrate"],
                "provenance_origin": manifest_json["provenance_origin"],
                "source_risk": manifest_json["source_risk"],
                "side_effect_class": manifest_json["side_effect_class"],
                "promotion_state": manifest_json.get("promotion_state"),
                "review_status": evidence_packet.get("review_status") if evidence_packet else None,
                "evidence_packet_id": evidence_packet.get("evidence_packet_id") if evidence_packet else None,
                "evidence_packet_digest": evidence_packet.get("evidence_packet_digest") if evidence_packet else None,
                "evidence_expires_at": evidence_packet.get("evidence_expires_at") if evidence_packet else None,
                "public_claim_boundary": manifest_json["public_claim_boundary"],
                "manifest_json": manifest_json,
                "evidence_packet_json": evidence_packet,
                "owner": manifest_json.get("owner"),
                "reviewer": manifest_json.get("reviewer"),
                "expires_at": manifest_json.get("expires_at"),
            }
        )

    rows.sort(key=lambda row: (str(row["capability_id"]), str(row["route_id"])))
    return rows


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _jsonb_literal(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{_sql_string_literal(encoded)}::jsonb"


def _sql_value(column: str, value: Any) -> str:
    if value is None:
        return "NULL"
    if column in _JSONB_COLUMNS:
        return _jsonb_literal(value)
    if column in _TIMESTAMPTZ_COLUMNS:
        return f"{_sql_string_literal(str(value))}::timestamptz"
    return _sql_string_literal(str(value))


def render_index_command_manifest_seed_sql() -> str:
    """Render the deterministic SQL migration for current PP-2 fixtures."""

    column_block = ",\n    ".join(_SEED_COLUMNS)
    values = []
    for row in index_command_manifest_seed_rows():
        row_values = ",\n        ".join(_sql_value(column, row[column]) for column in _SEED_COLUMNS)
        values.append(f"    (\n        {row_values}\n    )")

    values_block = ",\n".join(values)
    update_block = ",\n    ".join(
        f"{column} = EXCLUDED.{column}" for column in _SEED_COLUMNS if column != "route_id"
    )

    return (
        "-- Migration 0166: Seed hosted Index command manifest storage\n"
        "--\n"
        "-- Deterministic PP-2 fixture seed for index_command_manifests. These rows\n"
        "-- preserve manifest/evidence digests and public claim boundaries exactly;\n"
        "-- they do not claim live production execution. Evidence columns are filled\n"
        "-- only where an Index evidence packet fixture already exists.\n"
        "\n"
        "BEGIN;\n"
        "\n"
        "INSERT INTO index_command_manifests (\n"
        f"    {column_block}\n"
        ")\n"
        "VALUES\n"
        f"{values_block}\n"
        "ON CONFLICT (route_id) DO UPDATE SET\n"
        f"    {update_block},\n"
        "    updated_at = NOW();\n"
        "\n"
        "COMMIT;\n"
    )


__all__ = [
    "INDEX_COMMAND_MANIFEST_SEED_MIGRATION",
    "index_command_manifest_seed_rows",
    "render_index_command_manifest_seed_sql",
]
