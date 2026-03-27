"""Tests for launch/dashboard billing bootstrap hardening."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app as _shared_app
from routes.auth import _issue_jwt
from schemas.user import EMAIL_NO_TRIAL_CREDIT_POLICY, EMAIL_OTP_SIGNUP_METHOD


@pytest.mark.anyio
async def test_ensure_org_billing_bootstrap_creates_org_wallet_and_ledger() -> None:
    with (
        patch(
            "services.billing_bootstrap.settings.billing_bootstrap_starter_credits_cents",
            125,
        ),
        patch("services.billing_bootstrap._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.billing_bootstrap._sb_post", new_callable=AsyncMock) as mock_post,
        patch("services.billing_bootstrap.log_payment_event") as mock_metric,
    ):
        mock_get.side_effect = [[], []]
        mock_post.return_value = [{}]

        from services.billing_bootstrap import ensure_org_billing_bootstrap

        result = await ensure_org_billing_bootstrap(
            "org_bootstrap",
            email="launch@example.com",
            name="Launch Example",
        )

    assert result == {
        "org_created": True,
        "wallet_created": True,
        "seeded_credits_cents": 125,
    }
    assert mock_post.call_count == 3

    org_call = mock_post.call_args_list[0]
    assert org_call.args[0] == "orgs"
    assert org_call.args[1]["id"] == "org_bootstrap"
    assert org_call.args[1]["email"] == "launch@example.com"

    wallet_call = mock_post.call_args_list[1]
    assert wallet_call.args[0] == "org_credits"
    assert wallet_call.args[1]["org_id"] == "org_bootstrap"
    assert wallet_call.args[1]["balance_usd_cents"] == 125

    ledger_call = mock_post.call_args_list[2]
    assert ledger_call.args[0] == "credit_ledger"
    assert ledger_call.args[1]["amount_usd_cents"] == 125
    mock_metric.assert_called_once()


@pytest.mark.anyio
async def test_ensure_org_billing_bootstrap_is_idempotent_when_wallet_exists() -> None:
    with (
        patch("services.billing_bootstrap._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.billing_bootstrap._sb_post", new_callable=AsyncMock) as mock_post,
    ):
        mock_get.side_effect = [[{"id": "org_existing"}], [{"org_id": "org_existing"}]]

        from services.billing_bootstrap import ensure_org_billing_bootstrap

        result = await ensure_org_billing_bootstrap(
            "org_existing",
            email="existing@example.com",
            name="Existing Org",
        )

    assert result == {
        "org_created": False,
        "wallet_created": False,
        "seeded_credits_cents": 0,
    }
    mock_post.assert_not_called()


@pytest.mark.anyio
async def test_ensure_org_billing_bootstrap_forces_zero_credits_for_email_signup() -> None:
    with (
        patch(
            "services.billing_bootstrap.settings.billing_bootstrap_starter_credits_cents",
            125,
        ),
        patch("services.billing_bootstrap._sb_get", new_callable=AsyncMock) as mock_get,
        patch("services.billing_bootstrap._sb_post", new_callable=AsyncMock) as mock_post,
        patch("services.billing_bootstrap.log_payment_event") as mock_metric,
    ):
        mock_get.side_effect = [[], []]
        mock_post.return_value = [{}]

        from services.billing_bootstrap import ensure_org_billing_bootstrap

        result = await ensure_org_billing_bootstrap(
            "org_email",
            email="agent@example.com",
            name="Agent Example",
            starter_credits_cents=125,
            signup_method=EMAIL_OTP_SIGNUP_METHOD,
            credit_policy=EMAIL_NO_TRIAL_CREDIT_POLICY,
        )

    assert result == {
        "org_created": True,
        "wallet_created": True,
        "seeded_credits_cents": 0,
    }
    assert mock_post.call_count == 2

    wallet_call = mock_post.call_args_list[1]
    assert wallet_call.args[0] == "org_credits"
    assert wallet_call.args[1]["org_id"] == "org_email"
    assert wallet_call.args[1]["balance_usd_cents"] == 0
    mock_metric.assert_not_called()


def test_auth_me_self_heals_billing_bootstrap() -> None:
    session_token = _issue_jwt({
        "sub": "user_123",
        "email": "launch@example.com",
        "agent_id": "agent_123",
        "org_id": "org_launch",
    })
    client = TestClient(_shared_app)

    fake_user = SimpleNamespace(
        user_id="user_123",
        email="launch@example.com",
        name="Launch User",
        avatar_url="",
        provider="google",
        signup_method="oauth",
        credit_policy="oauth_trial",
        organization_id="org_launch",
        default_agent_id="agent_123",
        created_at="2026-03-26T00:00:00Z",
    )
    fake_agent = SimpleNamespace(api_key_prefix="rhumb_launch")

    with (
        patch("routes.auth.get_user_store") as mock_user_store_factory,
        patch("routes.auth.get_agent_identity_store") as mock_identity_factory,
        patch("routes.auth.ensure_org_billing_bootstrap", new_callable=AsyncMock) as mock_bootstrap,
    ):
        mock_user_store = mock_user_store_factory.return_value
        mock_user_store.get_user = AsyncMock(return_value=fake_user)

        mock_identity_store = mock_identity_factory.return_value
        mock_identity_store.get_agent = AsyncMock(return_value=fake_agent)

        response = client.get(
            "/v1/auth/me",
            cookies={"rhumb_session": session_token},
        )

    assert response.status_code == 200
    mock_bootstrap.assert_awaited_once_with(
        "org_launch",
        email="launch@example.com",
        name="Launch User",
        signup_method="oauth",
        credit_policy="oauth_trial",
    )
    assert response.json()["api_key_prefix"] == "rhumb_launch"
