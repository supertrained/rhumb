from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "audit_salesforce_bootstrap_hygiene.py"

spec = importlib.util.spec_from_file_location("audit_salesforce_bootstrap_hygiene", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
salesforce_hygiene = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = salesforce_hygiene
spec.loader.exec_module(salesforce_hygiene)


def test_audit_bundle_item_requires_scope_and_token_fields() -> None:
    item_payload = {
        "category": "API_CREDENTIAL",
        "fields": [
            {"label": "client_id", "value": "cid"},
            {"label": "client_secret", "value": "secret"},
            {"label": "refresh_token", "value": "refresh"},
            {"label": "auth_base_url", "value": "https://login.salesforce.com"},
            {"label": "redirect_uri", "value": "http://127.0.0.1:1717/callback"},
            {"label": "connected_app", "value": "Rhumb CRM Proof"},
            {"label": "account", "value": "ops@example.com"},
            {"label": "instance_url", "value": "https://acme.my.salesforce.com"},
            {"label": "allowed_object_types", "value": "Account"},
            {"label": "record_id", "value": "001ABC"},
        ],
    }

    with patch.object(salesforce_hygiene, "_load_item", return_value=(item_payload, None)):
        result = salesforce_hygiene.audit_bundle_item("Salesforce CRM Bundle - sf_main", "OpenClaw Agents")

    assert result["exists"] is True
    assert result["bundle_material_ready"] is False
    assert result["missing_required_fields"] == ["allowed_properties_by_object"]


def test_scan_temp_residue_marks_secret_bundle_export_as_high_risk(tmp_path: Path) -> None:
    high_risk = tmp_path / "railway_set_sf_main.sh"
    high_risk.write_text(
        "set -euo pipefail\nrailway variables set RHUMB_CRM_SF_MAIN='{\"refresh_token\":\"rtok\",\"client_secret\":\"secret\"}'\n"
    )
    low_risk = tmp_path / "salesforce-notes.txt"
    low_risk.write_text("salesforce bootstrap notes without any credential material\n")

    results = salesforce_hygiene.scan_temp_residue(tmp_path)
    by_name = {entry.path.name: entry for entry in results}

    assert by_name["railway_set_sf_main.sh"].high_risk is True
    assert by_name["railway_set_sf_main.sh"].secret_markers == (
        "refresh_token",
        "client_secret",
        "rhumb_crm_sf_main",
    )
    assert by_name["salesforce-notes.txt"].high_risk is False
    assert by_name["salesforce-notes.txt"].salesforce_markers == ("salesforce",)


def test_cleanup_residue_uses_trash_for_high_risk_files(tmp_path: Path) -> None:
    high_risk = salesforce_hygiene.ResidueScan(
        path=tmp_path / "railway_set_sf_main.sh",
        size_bytes=20,
        salesforce_markers=("sf_main",),
        secret_markers=("refresh_token",),
        high_risk=True,
    )
    benign = salesforce_hygiene.ResidueScan(
        path=tmp_path / "salesforce-notes.txt",
        size_bytes=20,
        salesforce_markers=("salesforce",),
        secret_markers=(),
        high_risk=False,
    )

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch.object(salesforce_hygiene.shutil, "which", return_value="/usr/bin/trash"), patch.object(
        salesforce_hygiene.subprocess,
        "run",
        side_effect=_fake_run,
    ):
        result = salesforce_hygiene.cleanup_residue([high_risk, benign])

    assert result == {
        "requested": True,
        "available": True,
        "cleaned_paths": [str(high_risk.path)],
        "errors": [],
    }
    assert calls == [["/usr/bin/trash", str(high_risk.path)]]
