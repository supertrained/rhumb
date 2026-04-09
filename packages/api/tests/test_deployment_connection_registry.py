"""Tests for the deployment_ref registry."""

from __future__ import annotations

import json

import pytest

from services.deployment_connection_registry import (
    DeploymentRefError,
    ensure_deployment_access,
    ensure_requested_project_allowed,
    ensure_target_allowed,
    resolve_deployment_bundle,
)


def test_resolve_deployment_bundle_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_DEPLOYMENT_DEP_MAIN",
        json.dumps(
            {
                "provider": "vercel",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "team_id": "team_123",
                "allowed_project_ids": ["prj_123"],
                "allowed_targets": ["production", "preview"],
            }
        ),
    )

    bundle = resolve_deployment_bundle("dep_main")
    assert bundle.provider == "vercel"
    assert bundle.auth_mode == "bearer_token"
    assert bundle.team_id == "team_123"
    assert bundle.allowed_project_ids == ("prj_123",)
    assert bundle.allowed_targets == ("production", "preview")


def test_resolve_deployment_bundle_requires_project_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_DEPLOYMENT_DEP_MAIN",
        json.dumps(
            {
                "provider": "vercel",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
            }
        ),
    )

    with pytest.raises(DeploymentRefError, match="must declare at least one allowed_project_ids"):
        resolve_deployment_bundle("dep_main")


def test_requested_project_must_be_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_DEPLOYMENT_DEP_MAIN",
        json.dumps(
            {
                "provider": "vercel",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_project_ids": ["prj_123"],
            }
        ),
    )

    bundle = resolve_deployment_bundle("dep_main")
    with pytest.raises(DeploymentRefError, match="project 'prj_999'"):
        ensure_requested_project_allowed(bundle, "prj_999")


def test_target_must_be_allowlisted_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_DEPLOYMENT_DEP_MAIN",
        json.dumps(
            {
                "provider": "vercel",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_project_ids": ["prj_123"],
                "allowed_targets": ["production"],
            }
        ),
    )

    bundle = resolve_deployment_bundle("dep_main")
    with pytest.raises(DeploymentRefError, match="target 'preview'"):
        ensure_target_allowed(bundle, "preview")


def test_ensure_deployment_access_rejects_out_of_scope_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "RHUMB_DEPLOYMENT_DEP_MAIN",
        json.dumps(
            {
                "provider": "vercel",
                "auth_mode": "bearer_token",
                "bearer_token": "secret-token",
                "allowed_project_ids": ["prj_123"],
            }
        ),
    )

    bundle = resolve_deployment_bundle("dep_main")
    with pytest.raises(DeploymentRefError, match="deployment 'dpl_123'"):
        ensure_deployment_access(
            bundle,
            {"uid": "dpl_123", "projectId": "prj_999", "target": "production"},
            deployment_id="dpl_123",
        )
