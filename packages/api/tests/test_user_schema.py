"""Focused tests for the unified user schema/store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from schemas.user import (
    EMAIL_AUTH_PROVIDER,
    EMAIL_NO_TRIAL_CREDIT_POLICY,
    EMAIL_OTP_SIGNUP_METHOD,
    OAUTH_SIGNUP_METHOD,
    OAUTH_TRIAL_CREDIT_POLICY,
    UserStore,
    build_email_provider_id,
    has_verified_email,
    is_email_signup,
)


@pytest.mark.anyio
async def test_create_oauth_user_defaults_verified_email_and_trial_policy() -> None:
    store = UserStore(supabase_client=None)

    user = await store.create_user(
        email="oauth@example.com",
        name="OAuth Example",
        provider="google",
        provider_id="google-user-1",
    )

    assert user.signup_method == OAUTH_SIGNUP_METHOD
    assert user.credit_policy == OAUTH_TRIAL_CREDIT_POLICY
    assert user.email_verified_at is not None
    assert has_verified_email(user) is True
    assert is_email_signup(user) is False
    assert user.risk_flags == {}


@pytest.mark.anyio
async def test_create_email_otp_user_persists_explicit_auth_and_credit_policy_fields() -> None:
    store = UserStore(supabase_client=None)
    verified_at = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)

    user = await store.create_user(
        email="agent@example.com",
        name="Snowy",
        provider=EMAIL_AUTH_PROVIDER,
        provider_id=build_email_provider_id("agent@example.com"),
        signup_method=EMAIL_OTP_SIGNUP_METHOD,
        email_verified_at=verified_at,
        signup_ip="203.0.113.7",
        signup_subnet="203.0.113.0/24",
        credit_policy=EMAIL_NO_TRIAL_CREDIT_POLICY,
        risk_flags={"disposable_domain": False},
    )

    fetched = await store.find_by_email("agent@example.com")

    assert fetched is not None
    assert fetched.provider == EMAIL_AUTH_PROVIDER
    assert fetched.provider_id == "email:agent@example.com"
    assert fetched.signup_method == EMAIL_OTP_SIGNUP_METHOD
    assert fetched.email_verified_at == verified_at
    assert fetched.signup_ip == "203.0.113.7"
    assert fetched.signup_subnet == "203.0.113.0/24"
    assert fetched.credit_policy == EMAIL_NO_TRIAL_CREDIT_POLICY
    assert fetched.risk_flags == {"disposable_domain": False}
    assert has_verified_email(fetched) is True
    assert is_email_signup(fetched) is True
