"""Tests for the actions_ref registry."""

from __future__ import annotations

import json

import pytest

from services.actions_connection_registry import (
    ActionsRefError,
    ensure_repository_allowed,
    resolve_actions_bundle,
    split_repository,
)


def test_resolve_actions_bundle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_ACTIONS_GH_MAIN",
        json.dumps(
            {
                "provider": "github",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_repositories": ["OpenClaw/OpenClaw", "rhumb-dev/api"],
            }
        ),
    )

    bundle = resolve_actions_bundle("gh_main")
    assert bundle.provider == "github"
    assert bundle.auth_mode == "bearer_token"
    assert bundle.allowed_repositories == ("openclaw/openclaw", "rhumb-dev/api")


def test_resolve_actions_bundle_requires_repository_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_ACTIONS_GH_MAIN",
        json.dumps(
            {
                "provider": "github",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
            }
        ),
    )

    with pytest.raises(ActionsRefError, match="must declare at least one allowed_repositories"):
        resolve_actions_bundle("gh_main")


def test_requested_repository_must_be_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_ACTIONS_GH_MAIN",
        json.dumps(
            {
                "provider": "github",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_repositories": ["openclaw/openclaw"],
            }
        ),
    )

    bundle = resolve_actions_bundle("gh_main")
    with pytest.raises(ActionsRefError, match="repository 'octo/test'"):
        ensure_repository_allowed(bundle, "octo/test")


def test_split_repository_normalizes_case() -> None:
    owner, repo = split_repository("OpenClaw/OpenClaw")
    assert owner == "openclaw"
    assert repo == "openclaw"
