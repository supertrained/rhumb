"""Tests for Intercom support_ref registry behavior."""

from __future__ import annotations

import json

import pytest

from services.support_connection_registry import (
    SupportRefError,
    conversation_in_scope,
    ensure_conversation_access,
    resolve_intercom_support_bundle,
    resolve_support_bundle,
)


def test_resolve_support_bundle_intercom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_CHAT",
        json.dumps(
            {
                "provider": "intercom",
                "region": "us",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_team_ids": [123],
                "allowed_admin_ids": [456],
                "allow_internal_notes": False,
            }
        ),
    )

    bundle = resolve_support_bundle("sup_chat")
    assert bundle.provider == "intercom"
    assert bundle.region == "us"
    assert bundle.allowed_team_ids == (123,)
    assert bundle.allowed_admin_ids == (456,)
    assert bundle.allow_internal_notes is False

    direct_bundle = resolve_intercom_support_bundle("sup_chat")
    assert direct_bundle.bearer_token == "secret-token"


def test_resolve_support_bundle_intercom_requires_scope_constraint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_CHAT",
        json.dumps(
            {
                "provider": "intercom",
                "region": "us",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
            }
        ),
    )

    with pytest.raises(SupportRefError, match="must declare at least one scope constraint"):
        resolve_intercom_support_bundle("sup_chat")


def test_conversation_in_scope_requires_all_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_CHAT",
        json.dumps(
            {
                "provider": "intercom",
                "region": "us",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_team_ids": [123],
                "allowed_admin_ids": [456],
            }
        ),
    )

    bundle = resolve_intercom_support_bundle("sup_chat")
    assert conversation_in_scope(bundle, {"id": "conv_1", "team_assignee_id": 123, "admin_assignee_id": 456}) is True
    assert conversation_in_scope(bundle, {"id": "conv_1", "team_assignee_id": 999, "admin_assignee_id": 456}) is False
    assert conversation_in_scope(bundle, {"id": "conv_1", "team_assignee_id": 123, "admin_assignee_id": 999}) is False


def test_ensure_conversation_access_rejects_out_of_scope_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_CHAT",
        json.dumps(
            {
                "provider": "intercom",
                "region": "us",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_team_ids": [123],
            }
        ),
    )

    bundle = resolve_intercom_support_bundle("sup_chat")
    with pytest.raises(SupportRefError, match="not allowed to access conversation 'conv_55'"):
        ensure_conversation_access(
            bundle,
            {"id": "conv_55", "team_assignee_id": 999},
            conversation_id="conv_55",
        )
