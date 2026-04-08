"""Tests for the DB connection registry."""

from __future__ import annotations

import os

import pytest

from services.db_connection_registry import (
    AgentVaultDsnError,
    ConnectionRefError,
    detect_postgres_provider,
    resolve_agent_vault_dsn,
    resolve_dsn,
    validate_connection_ref,
)


def test_resolve_dsn_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "postgresql://reader:pass@localhost:5432/app")
    assert resolve_dsn("conn_reader") == "postgresql://reader:pass@localhost:5432/app"


def test_resolve_dsn_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)
    with pytest.raises(ConnectionRefError, match="No DSN configured"):
        resolve_dsn("conn_reader")


def test_resolve_dsn_rejects_disabled_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "disabled")
    with pytest.raises(ConnectionRefError, match="disabled or invalid"):
        resolve_dsn("conn_reader")


def test_resolve_dsn_rejects_invalid_identifier() -> None:
    with pytest.raises(ConnectionRefError, match="Invalid connection_ref"):
        resolve_dsn("conn;drop")


def test_resolve_dsn_rejects_uppercase() -> None:
    with pytest.raises(ConnectionRefError, match="Invalid connection_ref"):
        resolve_dsn("CONN_READER")


def test_resolve_dsn_rejects_empty() -> None:
    with pytest.raises(ConnectionRefError, match="Invalid connection_ref"):
        resolve_dsn("")


def test_resolve_dsn_accepts_underscores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_DB_MY_APP_READ", "postgresql://localhost/myapp")
    assert resolve_dsn("my_app_read") == "postgresql://localhost/myapp"


def test_validate_connection_ref_accepts_simple_value() -> None:
    validate_connection_ref("conn_reader")


def test_resolve_agent_vault_dsn_requires_token() -> None:
    with pytest.raises(AgentVaultDsnError, match="X-Agent-Token"):
        resolve_agent_vault_dsn(None)


def test_resolve_agent_vault_dsn_rejects_non_postgres_scheme() -> None:
    with pytest.raises(AgentVaultDsnError, match="postgresql"):
        resolve_agent_vault_dsn("https://example.com")


def test_resolve_agent_vault_dsn_accepts_postgres_url() -> None:
    dsn = "postgresql://reader:pass@localhost:5432/app"
    assert resolve_agent_vault_dsn(dsn) == dsn


def test_detect_postgres_provider_defaults_to_postgresql() -> None:
    assert detect_postgres_provider("postgresql://reader:pass@localhost:5432/app") == "postgresql"


@pytest.mark.parametrize(
    ("dsn", "expected_provider"),
    [
        (
            "postgresql://postgres:pass@db.abcdefghijklmnop.supabase.co:5432/postgres",
            "supabase",
        ),
        (
            "postgresql://postgres.project-ref:pass@aws-0-us-west-1.pooler.supabase.com:6543/postgres",
            "supabase",
        ),
    ],
)
def test_detect_postgres_provider_recognizes_supabase_hosts(
    dsn: str,
    expected_provider: str,
) -> None:
    assert detect_postgres_provider(dsn) == expected_provider
