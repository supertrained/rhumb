"""Tests for the support_ref registry."""

from __future__ import annotations

import json

import pytest

from services.support_connection_registry import (
    SupportRefError,
    ensure_ticket_access,
    resolve_support_bundle,
    ticket_in_scope,
)


def test_resolve_support_bundle_api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme-support",
                "auth_mode": "api_token",
                "email": "ops@acme.com",
                "api_token": "secret-token",
                "allowed_group_ids": [123],
                "allow_internal_comments": False,
            }
        ),
    )

    bundle = resolve_support_bundle("sup_help")
    assert bundle.support_ref == "sup_help"
    assert bundle.provider == "zendesk"
    assert bundle.auth_mode == "api_token"
    assert bundle.email == "ops@acme.com"
    assert bundle.api_token == "secret-token"
    assert bundle.allowed_group_ids == (123,)
    assert bundle.allowed_brand_ids == ()
    assert bundle.allow_internal_comments is False


def test_resolve_support_bundle_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme",
                "auth_mode": "bearer_token",
                "bearer_token": "bearer-secret",
                "allowed_brand_ids": [456],
                "allow_internal_comments": True,
            }
        ),
    )

    bundle = resolve_support_bundle("sup_help")
    assert bundle.auth_mode == "bearer_token"
    assert bundle.bearer_token == "bearer-secret"
    assert bundle.allowed_group_ids == ()
    assert bundle.allowed_brand_ids == (456,)
    assert bundle.allow_internal_comments is True


def test_resolve_support_bundle_requires_scope_constraint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme",
                "auth_mode": "bearer_token",
                "bearer_token": "bearer-secret",
            }
        ),
    )

    with pytest.raises(SupportRefError, match="must declare at least one scope constraint"):
        resolve_support_bundle("sup_help")


def test_ticket_in_scope_requires_all_configured_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme",
                "auth_mode": "bearer_token",
                "bearer_token": "bearer-secret",
                "allowed_group_ids": [123],
                "allowed_brand_ids": [456],
            }
        ),
    )

    bundle = resolve_support_bundle("sup_help")
    assert ticket_in_scope(bundle, {"id": 10, "group_id": 123, "brand_id": 456}) is True
    assert ticket_in_scope(bundle, {"id": 10, "group_id": 999, "brand_id": 456}) is False
    assert ticket_in_scope(bundle, {"id": 10, "group_id": 123, "brand_id": 999}) is False


def test_ensure_ticket_access_rejects_out_of_scope_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_SUPPORT_SUP_HELP",
        json.dumps(
            {
                "provider": "zendesk",
                "subdomain": "acme",
                "auth_mode": "bearer_token",
                "bearer_token": "bearer-secret",
                "allowed_group_ids": [123],
            }
        ),
    )

    bundle = resolve_support_bundle("sup_help")
    with pytest.raises(SupportRefError, match="not allowed to access ticket '55'"):
        ensure_ticket_access(bundle, {"id": 55, "group_id": 999}, ticket_id=55)
