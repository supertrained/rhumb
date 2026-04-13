from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_db_agent_vault_token.py"

spec = importlib.util.spec_from_file_location("build_db_agent_vault_token", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
build_db_agent_vault_token = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_db_agent_vault_token)


def test_main_prints_signed_token_with_explicit_bindings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def _fake_issue_token(
        dsn: str,
        *,
        connection_ref: str,
        agent_id: str | None = None,
        org_id: str | None = None,
        ttl_seconds: int = 300,
    ) -> str:
        captured.update(
            {
                "dsn": dsn,
                "connection_ref": connection_ref,
                "agent_id": agent_id,
                "org_id": org_id,
                "ttl_seconds": ttl_seconds,
            }
        )
        return "rhdbv1.test-token"

    monkeypatch.setattr(build_db_agent_vault_token, "issue_agent_vault_dsn_token", _fake_issue_token)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_db_agent_vault_token.py",
            "--connection-ref",
            "conn_reader",
            "--dsn",
            "postgresql://user:pass@db.example.com:5432/app",
            "--agent-id",
            "agent_123",
            "--org-id",
            "org_456",
            "--ttl-seconds",
            "120",
        ],
    )

    assert build_db_agent_vault_token.main() == 0
    assert capsys.readouterr().out.strip() == "rhdbv1.test-token"
    assert captured == {
        "dsn": "postgresql://user:pass@db.example.com:5432/app",
        "connection_ref": "conn_reader",
        "agent_id": "agent_123",
        "org_id": "org_456",
        "ttl_seconds": 120,
    }


def test_main_uses_default_ttl_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def _fake_issue_token(
        dsn: str,
        *,
        connection_ref: str,
        agent_id: str | None = None,
        org_id: str | None = None,
        ttl_seconds: int = 300,
    ) -> str:
        captured["ttl_seconds"] = ttl_seconds
        return "rhdbv1.default-ttl"

    monkeypatch.setattr(build_db_agent_vault_token, "issue_agent_vault_dsn_token", _fake_issue_token)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_db_agent_vault_token.py",
            "--connection-ref",
            "conn_reader",
            "--dsn",
            "postgresql://user:pass@db.example.com:5432/app",
        ],
    )

    assert build_db_agent_vault_token.main() == 0
    assert capsys.readouterr().out.strip() == "rhdbv1.default-ttl"
    assert captured["ttl_seconds"] == 300
