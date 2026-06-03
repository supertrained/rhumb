"""PP-1/PP-2 hosted Index manifest seed tests."""

from __future__ import annotations

from pathlib import Path

from schemas.capability_manifest import command_manifest_fixtures
from schemas.index_evidence import route_fixture_for
from services.index_manifest_seed import (
    index_command_manifest_seed_rows,
    render_index_command_manifest_seed_sql,
)
from services.index_manifest_store import _manifest_from_row, _route_facts_from_row, with_recommendation_policy


def _rows_by_route_id() -> dict[str, dict]:
    return {row["route_id"]: row for row in index_command_manifest_seed_rows()}


def test_seed_rows_cover_pp2_fixtures_and_preserve_manifest_digests() -> None:
    fixtures = {manifest["route_id"]: manifest for manifest in command_manifest_fixtures()}
    rows = _rows_by_route_id()

    assert set(rows) == set(fixtures)
    assert len(rows) == 9

    for route_id, manifest in fixtures.items():
        row = rows[route_id]
        assert row["manifest_json"] == manifest
        assert row["manifest_digest"] == manifest["manifest_digest"]
        assert row["public_claim_boundary"] == manifest["public_claim_boundary"]
        assert row["promotion_state"] == manifest["promotion_state"]
        assert row["owner"] == manifest["owner"]
        assert row["reviewer"] == manifest["reviewer"]
        assert row["expires_at"] == manifest["expires_at"]


def test_seed_rows_preserve_evidence_metadata_only_where_available() -> None:
    rows = _rows_by_route_id()
    search_row = rows["route_search_query_brave_search_api_official_api_v1"]
    fixture = route_fixture_for("search.query", "brave-search-api")
    assert fixture is not None
    evidence = fixture["evidence_packet"]

    assert search_row["evidence_packet_json"] == evidence
    assert search_row["evidence_packet_id"] == evidence["evidence_packet_id"]
    assert search_row["evidence_packet_digest"] == evidence["evidence_packet_digest"]
    assert search_row["evidence_expires_at"] == evidence["evidence_expires_at"]
    assert search_row["review_status"] == "current"

    rows_without_evidence = [row for row in rows.values() if row["route_id"] != search_row["route_id"]]
    assert rows_without_evidence
    assert all(row["evidence_packet_json"] is None for row in rows_without_evidence)
    assert all(row["evidence_packet_digest"] is None for row in rows_without_evidence)
    assert all(row["review_status"] is None for row in rows_without_evidence)


def test_seed_sql_matches_both_migration_files() -> None:
    expected_sql = render_index_command_manifest_seed_sql()
    for path in (
        Path("packages/api/migrations/0166_index_command_manifest_seed.sql"),
        Path("supabase/migrations/0166_index_command_manifest_seed.sql"),
    ):
        assert path.read_text(encoding="utf-8") == expected_sql


def test_seeded_rows_hydrate_route_facts_and_fail_closed_recommendation_policy() -> None:
    rows = _rows_by_route_id()

    search_facts = _route_facts_from_row(rows["route_search_query_brave_search_api_official_api_v1"])
    assert search_facts["manifest_digest"].startswith("sha256:")
    assert search_facts["evidence_packet_id"] == "evidence_search_query_brave_search_api_official_api_2026_05_19"
    assert search_facts["recommendation_policy"]["default_recommendable"] is True

    generated = with_recommendation_policy(_manifest_from_row(rows["route_calendar_freebusy_generated_adapter_v1"]))
    assert generated["recommendation_policy"]["default_recommendable"] is False
    assert generated["recommendation_policy"]["requires_explicit_request"] is True
    assert "generated_route_not_default" in generated["recommendation_policy"]["reasons"]
    assert "source_risk_community_unverified_not_default" in generated["recommendation_policy"]["reasons"]

    write_route = with_recommendation_policy(_manifest_from_row(rows["route_support_ticket_create_zendesk_api_official_api_v1"]))
    assert write_route["recommendation_policy"]["default_recommendable"] is False
    assert write_route["recommendation_policy"]["requires_explicit_request"] is True
    assert "high_risk_side_effect_not_default" in write_route["recommendation_policy"]["reasons"]

    cli_route = with_recommendation_policy(_manifest_from_row(rows["route_workflow_run_list_github_cli_v1"]))
    assert cli_route["recommendation_policy"]["default_recommendable"] is False
    assert "source_risk_community_unverified_not_default" in cli_route["recommendation_policy"]["reasons"]
