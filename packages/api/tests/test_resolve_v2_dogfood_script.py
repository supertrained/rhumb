"""Tests for the Resolve v2 dogfood operator harness."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import call, patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "resolve_v2_dogfood.py"

spec = importlib.util.spec_from_file_location("resolve_v2_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
resolve_v2_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolve_v2_dogfood)


def test_build_l2_execute_payload_defaults_to_provider_preference():
    payload = resolve_v2_dogfood.build_l2_execute_payload(
        parameters={"query": "rhumb"},
        provider="brave-search-api",
        credential_mode="rhumb_managed",
        interface="dogfood",
        max_cost_usd=0.05,
        provider_preference=None,
    )

    assert payload == {
        "parameters": {"query": "rhumb"},
        "credential_mode": "rhumb_managed",
        "interface": "dogfood",
        "policy": {
            "max_cost_usd": 0.05,
            "provider_preference": ["brave-search-api"],
        },
    }


def test_build_l1_execute_payload_sets_idempotency_and_optional_policy():
    payload = resolve_v2_dogfood.build_l1_execute_payload(
        capability="search.query",
        parameters={"query": "rhumb"},
        credential_mode="rhumb_managed",
        interface="dogfood",
        max_cost_usd=0.05,
    )

    assert payload["capability"] == "search.query"
    assert payload["parameters"] == {"query": "rhumb"}
    assert payload["credential_mode"] == "rhumb_managed"
    assert payload["interface"] == "dogfood"
    assert payload["policy"] == {"max_cost_usd": 0.05}
    assert payload["idempotency_key"].startswith("dogfood-")


def test_extract_receipt_and_explanation_ids_from_v2_payload():
    data = {
        "execution_id": "exec_123",
        "_rhumb_v2": {
            "receipt_id": "rcpt_nested",
            "explanation_id": "expl_123",
        },
    }

    assert resolve_v2_dogfood.extract_execution_id(data) == "exec_123"
    assert resolve_v2_dogfood.extract_receipt_id(data) == "rcpt_nested"
    assert resolve_v2_dogfood.extract_explanation_id(data) == "expl_123"


def test_extract_receipt_id_prefers_top_level_receipt_id():
    data = {
        "receipt_id": "rcpt_top",
        "_rhumb": {"receipt_id": "rcpt_old"},
        "_rhumb_v2": {"receipt_id": "rcpt_nested"},
    }

    assert resolve_v2_dogfood.extract_receipt_id(data) == "rcpt_top"


def test_get_api_key_uses_env_first():
    with patch.dict(resolve_v2_dogfood.os.environ, {"RHUMB_DOGFOOD_API_KEY": "rhumb_env_key"}, clear=True):
        assert resolve_v2_dogfood._get_api_key("RHUMB_DOGFOOD_API_KEY") == "rhumb_env_key"


def test_get_api_key_falls_back_to_sop_when_env_missing():
    with (
        patch.dict(resolve_v2_dogfood.os.environ, {}, clear=True),
        patch.object(resolve_v2_dogfood, "_load_api_key_from_sop", return_value="rhumb_sop_key"),
    ):
        assert resolve_v2_dogfood._get_api_key("RHUMB_DOGFOOD_API_KEY") == "rhumb_sop_key"


def test_get_admin_key_uses_primary_env_first():
    with patch.dict(resolve_v2_dogfood.os.environ, {"RHUMB_ADMIN_SECRET": "admin_primary"}, clear=True):
        assert resolve_v2_dogfood._get_admin_key("RHUMB_ADMIN_SECRET") == "admin_primary"


def test_get_admin_key_falls_back_to_legacy_env_name():
    with patch.dict(resolve_v2_dogfood.os.environ, {"RHUMB_ADMIN_KEY": "admin_legacy"}, clear=True):
        assert resolve_v2_dogfood._get_admin_key("RHUMB_ADMIN_SECRET") == "admin_legacy"


def test_get_admin_key_falls_back_to_sop_when_env_missing():
    with (
        patch.dict(resolve_v2_dogfood.os.environ, {}, clear=True),
        patch.object(resolve_v2_dogfood, "_load_admin_key_from_sop", return_value="admin_sop"),
    ):
        assert resolve_v2_dogfood._get_admin_key("RHUMB_ADMIN_SECRET") == "admin_sop"


def test_build_summary_mentions_l1_and_l2_receipts():
    summary = resolve_v2_dogfood._build_summary({
        "config": {
            "capability": "search.query",
            "provider": "brave-search-api",
        },
        "layer2": {
            "execute": {
                "data": {
                    "execution_id": "exec_l2",
                    "provider_used": "brave-search-api",
                    "receipt_id": "rcpt_l2",
                }
            },
            "receipt": {"receipt_id": "rcpt_l2"},
        },
        "layer1": {
            "execute": {
                "data": {
                    "execution_id": "exec_l1",
                    "receipt_id": "rcpt_l1",
                }
            },
            "receipt": {"receipt_id": "rcpt_l1"},
        },
        "billing": {
            "summary": {"data": {"events_count": 4}},
        },
        "audit": {
            "status": {"data": {"total_events": 7}},
        },
    })

    assert "Resolve v2 dogfood complete" in summary
    assert "L2 search.query via brave-search-api exec=exec_l2 receipt=rcpt_l2" in summary
    assert "L1 provider=brave-search-api exec=exec_l1 receipt=rcpt_l1" in summary
    assert "billing_events=4" in summary
    assert "audit_events=7" in summary


def test_print_summary_only_emits_single_line(capsys):
    resolve_v2_dogfood._print_summary_only(
        {
            "ok": True,
            "summary": "Resolve v2 dogfood complete; L2 search.query via brave-search exec=exec_l2 receipt=rcpt_l2",
        }
    )

    captured = capsys.readouterr()
    assert (
        captured.out
        == "Resolve v2 dogfood complete; L2 search.query via brave-search exec=exec_l2 receipt=rcpt_l2\n"
    )


def test_apply_profile_defaults_sets_interface_and_parameters_from_profile():
    args = resolve_v2_dogfood.parse_args([])

    profiled = resolve_v2_dogfood._apply_profile_defaults(args, "beacon")

    assert profiled.profile == "beacon"
    assert profiled.interface == "dogfood-beacon"
    assert profiled.provider == "brave-search"
    assert profiled.capability == "search.query"
    assert profiled.parameters_json == '{"query": "best MCP server distribution channels for developers", "numResults": 3}'


def test_parse_args_accepts_summary_only_flag():
    args = resolve_v2_dogfood.parse_args(["--summary-only"])

    assert args.summary_only is True


def test_parse_args_accepts_refresh_stale_profiles_flag():
    args = resolve_v2_dogfood.parse_args(["--fleet-status", "--refresh-stale-profiles"])

    assert args.fleet_status is True
    assert args.refresh_stale_profiles is True


def test_apply_profile_defaults_preserves_explicit_interface_and_parameters():
    args = resolve_v2_dogfood.parse_args(
        [
            "--interface",
            "custom-interface",
            "--parameters-json",
            '{"query": "custom", "numResults": 1}',
        ]
    )

    profiled = resolve_v2_dogfood._apply_profile_defaults(args, "keel")

    assert profiled.interface == "custom-interface"
    assert profiled.parameters_json == '{"query": "custom", "numResults": 1}'


def test_build_batch_summary_mentions_profile_statuses():
    summary = resolve_v2_dogfood._build_batch_summary(
        {
            "pedro": {
                "ok": True,
                "config": {"provider": "brave-search", "interface": "dogfood-pedro"},
            },
            "beacon": {
                "ok": False,
                "config": {"provider": "brave-search", "interface": "dogfood-beacon"},
            },
        }
    )

    assert "Resolve v2 dogfood batch complete; ok_profiles=1/2" in summary
    assert "pedro=ok provider=brave-search interface=dogfood-pedro" in summary
    assert "beacon=failed provider=brave-search interface=dogfood-beacon" in summary


def test_build_fleet_status_entry_marks_profile_ok(tmp_path):
    artifact_path = tmp_path / "resolve-v2-dogfood-keel-admin-latest.json"
    artifact_path.write_text(
        json.dumps(
            {
                "ok": True,
                "started_at": 1_700_000_000,
                "summary": "Resolve v2 dogfood complete",
                "config": {
                    "provider": "brave-search",
                    "interface": "dogfood-keel",
                },
                "layer2": {"execute": {"data": {"execution_id": "exec_l2", "receipt_id": "rcpt_l2"}}},
                "layer1": {"execute": {"data": {"execution_id": "exec_l1", "receipt_id": "rcpt_l1"}}},
                "billing": {"summary": {"data": {"events_count": 4}}},
                "audit": {"status": {"data": {"total_events": 2}}},
                "receipt_chain": {"chain_intact": True, "verified": 20, "total_checked": 20},
            }
        ),
        encoding="utf-8",
    )

    with patch.object(resolve_v2_dogfood, "_artifact_root", return_value=tmp_path):
        entry = resolve_v2_dogfood._build_fleet_status_entry(
            "keel",
            artifact_path,
            now_ts=1_700_000_300,
            max_age_minutes=60,
        )

    expected_artifact_path = f"{tmp_path.name}/resolve-v2-dogfood-keel-admin-latest.json"
    assert entry == {
        "profile": "keel",
        "artifact_path": expected_artifact_path,
        "max_age_minutes": 60,
        "ok": True,
        "artifact_ok": True,
        "fresh": True,
        "started_at": 1_700_000_000,
        "started_at_iso": "2023-11-14T22:13:20Z",
        "age_minutes": 5.0,
        "provider": "brave-search",
        "interface": "dogfood-keel",
        "summary": "Resolve v2 dogfood complete",
        "billing_events": 4,
        "audit_events": 2,
        "chain_intact": True,
        "receipt_chain_verified": 20,
        "receipt_chain_checked": 20,
        "layer2_execution_id": "exec_l2",
        "layer2_receipt_id": "rcpt_l2",
        "layer1_execution_id": "exec_l1",
        "layer1_receipt_id": "rcpt_l1",
        "blocker": None,
    }


def test_build_fleet_status_entry_marks_missing_artifact_failed(tmp_path):
    missing_path = tmp_path / "resolve-v2-dogfood-beacon-admin-latest.json"

    with patch.object(resolve_v2_dogfood, "_artifact_root", return_value=tmp_path):
        entry = resolve_v2_dogfood._build_fleet_status_entry(
            "beacon",
            missing_path,
            now_ts=1_700_000_300,
            max_age_minutes=60,
        )

    expected_artifact_path = f"{tmp_path.name}/resolve-v2-dogfood-beacon-admin-latest.json"
    assert entry == {
        "profile": "beacon",
        "artifact_path": expected_artifact_path,
        "max_age_minutes": 60,
        "ok": False,
        "artifact_ok": False,
        "fresh": False,
        "blocker": "latest artifact missing",
    }


def test_build_fleet_status_summary_mentions_age_and_freshness_window():
    summary = resolve_v2_dogfood._build_fleet_status_summary(
        {
            "keel": {"ok": True, "provider": "brave-search", "age_minutes": 5.0},
            "helm": {"ok": False, "provider": "brave-search", "age_minutes": 1200.0},
        },
        1080,
    )

    assert "Resolve v2 dogfood fleet status complete; ok_profiles=1/2; freshness_window_minutes=1080" in summary
    assert "keel=ok provider=brave-search age_min=5.0" in summary
    assert "helm=failed provider=brave-search age_min=1200.0" in summary


def test_run_fleet_status_refreshes_only_non_ok_profiles_and_recomputes_status(tmp_path):
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    (artifact_root / "resolve-v2-dogfood-keel-admin-latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "started_at": 1_700_000_000,
                "summary": "stale keel",
                "config": {"provider": "brave-search", "interface": "dogfood-keel"},
                "receipt_chain": {"chain_intact": True, "verified": 1, "total_checked": 1},
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "resolve-v2-dogfood-helm-admin-latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "started_at": 1_700_066_770,
                "summary": "fresh helm",
                "config": {"provider": "brave-search", "interface": "dogfood-helm"},
                "receipt_chain": {"chain_intact": True, "verified": 1, "total_checked": 1},
            }
        ),
        encoding="utf-8",
    )

    args = resolve_v2_dogfood.parse_args(["--fleet-status", "--refresh-stale-profiles"])

    def fake_run_flow(run_args):
        return {
            "ok": True,
            "started_at": 1_700_066_790,
            "summary": f"refreshed {run_args.profile}",
            "config": {"provider": run_args.provider, "interface": run_args.interface},
            "receipt_chain": {"chain_intact": True, "verified": 2, "total_checked": 2},
        }

    with (
        patch.object(resolve_v2_dogfood, "_artifact_root", return_value=artifact_root),
        patch.object(resolve_v2_dogfood, "run_flow", side_effect=fake_run_flow) as mock_run_flow,
            patch.object(resolve_v2_dogfood.time, "time", side_effect=[1_700_066_800, 1_700_066_800]),
    ):
        payload = resolve_v2_dogfood.run_fleet_status(args, ["keel", "helm", "beacon"])

    assert payload["ok"] is True
    assert payload["refreshed_profiles"] == ["keel", "beacon"]
    assert {call_args.args[0].profile for call_args in mock_run_flow.call_args_list} == {"keel", "beacon"}
    assert payload["profiles"]["keel"]["ok"] is True
    assert payload["profiles"]["helm"]["ok"] is True
    assert payload["profiles"]["beacon"]["ok"] is True

    refreshed_keel = json.loads((artifact_root / "resolve-v2-dogfood-keel-admin-latest.json").read_text(encoding="utf-8"))
    refreshed_beacon = json.loads((artifact_root / "resolve-v2-dogfood-beacon-admin-latest.json").read_text(encoding="utf-8"))
    assert refreshed_keel["summary"] == "refreshed keel"
    assert refreshed_beacon["summary"] == "refreshed beacon"


def test_run_fleet_status_refresh_preserves_failure_when_rerun_still_fails(tmp_path):
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    (artifact_root / "resolve-v2-dogfood-keel-admin-latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "started_at": 1_700_000_000,
                "summary": "stale keel",
                "config": {"provider": "brave-search", "interface": "dogfood-keel"},
                "receipt_chain": {"chain_intact": True, "verified": 1, "total_checked": 1},
            }
        ),
        encoding="utf-8",
    )

    args = resolve_v2_dogfood.parse_args(["--fleet-status", "--refresh-stale-profiles"])

    with (
        patch.object(resolve_v2_dogfood, "_artifact_root", return_value=artifact_root),
        patch.object(
            resolve_v2_dogfood,
            "run_flow",
            side_effect=resolve_v2_dogfood.FlowError(
                "refresh failed",
                {"config": {"profile": "keel", "provider": "brave-search", "interface": "dogfood-keel"}},
            ),
        ),
        patch.object(resolve_v2_dogfood.time, "time", side_effect=[1_700_066_800, 1_700_066_800]),
    ):
        payload = resolve_v2_dogfood.run_fleet_status(args, ["keel"])

    assert payload["ok"] is False
    assert payload["refreshed_profiles"] == ["keel"]
    assert payload["profiles"]["keel"]["ok"] is False
    assert "artifact marked failed" in payload["profiles"]["keel"]["blocker"]

    refreshed_keel = json.loads((artifact_root / "resolve-v2-dogfood-keel-admin-latest.json").read_text(encoding="utf-8"))
    assert refreshed_keel["summary"] == "refresh failed"
    assert refreshed_keel["ok"] is False


def test_provision_api_key_via_admin_creates_agent_and_grants_access():
    args = resolve_v2_dogfood.argparse.Namespace(
        base_url="https://api.rhumb.dev",
        admin_key_env="RHUMB_ADMIN_SECRET",
        bootstrap_org_id="org_verify",
        bootstrap_agent_name="Verifier Agent",
        bootstrap_service=None,
        timeout=30.0,
    )

    responses = iter([
        {"status": 200, "json": []},
        {"status": 200, "json": {"agent_id": "agent_123", "api_key": "rhumb_new_key"}},
        {"status": 200, "json": {"access_id": "acc_123"}},
    ])

    with (
        patch.object(resolve_v2_dogfood, "_get_admin_key", return_value="admin_secret"),
        patch.object(resolve_v2_dogfood, "_http_json", side_effect=lambda *a, **k: next(responses)) as mock_http,
    ):
        api_key, metadata = resolve_v2_dogfood.provision_api_key_via_admin(args, provider="brave-search")

    assert api_key == "rhumb_new_key"
    assert metadata == {
        "organization_id": "org_verify",
        "agent_name": "Verifier Agent",
        "service": "brave-search",
        "list_attempts": 1,
        "mode": "created",
        "agent_id": "agent_123",
        "service_access": "granted",
    }
    assert mock_http.call_count == 3


def test_provision_api_key_via_admin_rotates_existing_agent_and_tolerates_existing_access():
    args = resolve_v2_dogfood.argparse.Namespace(
        base_url="https://api.rhumb.dev",
        admin_key_env="RHUMB_ADMIN_SECRET",
        bootstrap_org_id="org_verify",
        bootstrap_agent_name="Verifier Agent",
        bootstrap_service="brave-search",
        timeout=30.0,
    )

    responses = iter([
        {"status": 200, "json": [{"agent_id": "agent_existing", "name": "Verifier Agent"}]},
        {"status": 200, "json": {"new_api_key": "rhumb_rotated_key"}},
        {"status": 409, "json": {"detail": "already granted"}, "detail": "already granted"},
    ])

    with (
        patch.object(resolve_v2_dogfood, "_get_admin_key", return_value="admin_secret"),
        patch.object(resolve_v2_dogfood, "_http_json", side_effect=lambda *a, **k: next(responses)),
    ):
        api_key, metadata = resolve_v2_dogfood.provision_api_key_via_admin(args, provider="brave-search")

    assert api_key == "rhumb_rotated_key"
    assert metadata == {
        "organization_id": "org_verify",
        "agent_name": "Verifier Agent",
        "service": "brave-search",
        "list_attempts": 1,
        "mode": "rotated",
        "agent_id": "agent_existing",
        "service_access": "already_granted",
    }


def test_provision_api_key_via_admin_retries_transient_list_failure_once():
    args = resolve_v2_dogfood.argparse.Namespace(
        base_url="https://api.rhumb.dev",
        admin_key_env="RHUMB_ADMIN_SECRET",
        bootstrap_org_id="org_verify",
        bootstrap_agent_name="Verifier Agent",
        bootstrap_service="brave-search",
        timeout=30.0,
    )

    responses = iter([
        {"status": 500, "json": {"detail": "An unexpected error occurred."}},
        {"status": 200, "json": [{"agent_id": "agent_existing", "name": "Verifier Agent"}]},
        {"status": 200, "json": {"new_api_key": "rhumb_rotated_key"}},
        {"status": 409, "json": {"detail": "already granted"}, "detail": "already granted"},
    ])

    with (
        patch.object(resolve_v2_dogfood, "_get_admin_key", return_value="admin_secret"),
        patch.object(resolve_v2_dogfood, "_http_json", side_effect=lambda *a, **k: next(responses)) as mock_http,
        patch.object(resolve_v2_dogfood.time, "sleep") as mock_sleep,
    ):
        api_key, metadata = resolve_v2_dogfood.provision_api_key_via_admin(args, provider="brave-search")

    assert api_key == "rhumb_rotated_key"
    assert metadata == {
        "organization_id": "org_verify",
        "agent_name": "Verifier Agent",
        "service": "brave-search",
        "list_attempts": 2,
        "mode": "rotated",
        "agent_id": "agent_existing",
        "service_access": "already_granted",
    }
    assert mock_http.call_count == 4
    mock_sleep.assert_called_once_with(0.5)


def test_provision_api_key_via_admin_retries_multiple_transient_list_failures_before_success():
    args = resolve_v2_dogfood.argparse.Namespace(
        base_url="https://api.rhumb.dev",
        admin_key_env="RHUMB_ADMIN_SECRET",
        bootstrap_org_id="org_verify",
        bootstrap_agent_name="Verifier Agent",
        bootstrap_service="brave-search",
        timeout=30.0,
    )

    responses = iter([
        {"status": 500, "json": {"detail": "An unexpected error occurred."}},
        {"status": 500, "json": {"detail": "An unexpected error occurred."}},
        {"status": 500, "json": {"detail": "An unexpected error occurred."}},
        {"status": 200, "json": [{"agent_id": "agent_existing", "name": "Verifier Agent"}]},
        {"status": 200, "json": {"new_api_key": "rhumb_rotated_key"}},
        {"status": 409, "json": {"detail": "already granted"}, "detail": "already granted"},
    ])

    with (
        patch.object(resolve_v2_dogfood, "_get_admin_key", return_value="admin_secret"),
        patch.object(resolve_v2_dogfood, "_http_json", side_effect=lambda *a, **k: next(responses)) as mock_http,
        patch.object(resolve_v2_dogfood.time, "sleep") as mock_sleep,
    ):
        api_key, metadata = resolve_v2_dogfood.provision_api_key_via_admin(args, provider="brave-search")

    assert api_key == "rhumb_rotated_key"
    assert metadata == {
        "organization_id": "org_verify",
        "agent_name": "Verifier Agent",
        "service": "brave-search",
        "list_attempts": 4,
        "mode": "rotated",
        "agent_id": "agent_existing",
        "service_access": "already_granted",
    }
    assert mock_http.call_count == 6
    assert mock_sleep.call_args_list == [call(0.5), call(1.0), call(2.0)]



def test_provision_api_key_via_admin_surfaces_http_status_and_detail_on_list_failure():
    args = resolve_v2_dogfood.argparse.Namespace(
        base_url="https://api.rhumb.dev",
        admin_key_env="RHUMB_ADMIN_SECRET",
        bootstrap_org_id="org_verify",
        bootstrap_agent_name="Verifier Agent",
        bootstrap_service=None,
        timeout=30.0,
    )

    with (
        patch.object(resolve_v2_dogfood, "_get_admin_key", return_value="admin_secret"),
        patch.object(
            resolve_v2_dogfood,
            "_http_json",
            return_value={"status": 401, "json": {"detail": "Invalid or missing admin key."}},
        ),
    ):
        try:
            resolve_v2_dogfood.provision_api_key_via_admin(args, provider="brave-search")
        except RuntimeError as exc:
            assert str(exc) == "Admin agent list failed (401): Invalid or missing admin key."
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("Expected RuntimeError on admin list failure")
