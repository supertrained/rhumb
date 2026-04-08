"""Tests for the DB connection registry."""

from __future__ import annotations

import os

import pytest

from services.db_connection_registry import ConnectionRefError, resolve_dsn


def test_resolve_dsn_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "postgresql://reader:pass@localhost:5432/app")
    assert resolve_dsn("conn_reader") == "postgresql://reader:pass@localhost:5432/app"


def test_resolve_dsn_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)
    with pytest.raises(ConnectionRefError, match="No DSN configured"):
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
