"""Focused tests for the email OTP auth slice."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app as _shared_app
from schemas.agent_identity import AgentIdentityStore, reset_identity_store
from schemas.user import (
    EMAIL_AUTH_PROVIDER,
    EMAIL_NO_TRIAL_CREDIT_POLICY,
    EMAIL_OTP_SIGNUP_METHOD,
    OAUTH_SIGNUP_METHOD,
    UserStore,
    build_email_provider_id,
    reset_user_store,
)
from services.email_otp import EmailOtpService, ResendEmailOtpSender, reset_email_otp_service


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class RecordingEmailSender:
    """Capture OTP emails during tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str | int]] = []

    async def send_verification_code(self, *, email: str, code: str, ttl_minutes: int) -> None:
        self.calls.append(
            {
                "email": email,
                "code": code,
                "ttl_minutes": ttl_minutes,
            }
        )


@contextmanager
def _auth_email_harness(
    **otp_kwargs: int,
) -> Generator[SimpleNamespace, None, None]:
    reset_user_store()
    reset_identity_store()
    reset_email_otp_service()

    sender = RecordingEmailSender()
    user_store = UserStore(supabase_client=None)
    identity_store = AgentIdentityStore(supabase_client=None)
    otp_service = EmailOtpService(
        supabase_client=None,
        email_sender=sender,
        **otp_kwargs,
    )

    client = TestClient(_shared_app)

    with (
        patch("routes.auth.get_user_store", return_value=user_store),
        patch("routes.auth.get_agent_identity_store", return_value=identity_store),
        patch("routes.auth.get_email_otp_service", return_value=otp_service),
        patch("routes.auth.ensure_org_billing_bootstrap", new_callable=AsyncMock) as mock_bootstrap,
    ):
        yield SimpleNamespace(
            client=client,
            sender=sender,
            user_store=user_store,
            identity_store=identity_store,
            otp_service=otp_service,
            bootstrap=mock_bootstrap,
        )

    client.close()
    reset_user_store()
    reset_identity_store()
    reset_email_otp_service()


def test_request_code_returns_generic_success_for_new_email() -> None:
    with _auth_email_harness() as env:
        response = env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "Agent@Example.com"},
            headers={
                "origin": "https://rhumb.dev",
                "x-forwarded-for": "203.0.113.7",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "status": "ok",
            "message": "If the address can receive a sign-in code, it should arrive shortly.",
        },
        "error": None,
    }
    assert response.headers["access-control-allow-origin"] == "https://rhumb.dev"
    assert env.sender.calls == [
        {
            "email": "agent@example.com",
            "code": env.sender.calls[0]["code"],
            "ttl_minutes": 10,
        }
    ]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/v1/auth/email/request-code",
        "/v1/auth/email/verify-code",
    ],
)
def test_email_auth_rejects_non_object_bodies_before_auth_state(endpoint: str) -> None:
    client = TestClient(_shared_app)
    with (
        patch("routes.auth.get_user_store") as mock_user_store,
        patch("routes.auth.get_email_otp_service") as mock_otp_service,
        patch("routes.auth.get_agent_identity_store") as mock_identity_store,
        patch("routes.auth.ensure_org_billing_bootstrap", new_callable=AsyncMock) as mock_bootstrap,
    ):
        response = client.post(endpoint, json=[{"email": "agent@example.com"}])

    client.close()
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid email auth request body."
    assert payload["error"]["detail"] == "Provide a JSON object body."
    mock_user_store.assert_not_called()
    mock_otp_service.assert_not_called()
    mock_identity_store.assert_not_called()
    mock_bootstrap.assert_not_awaited()


def test_oauth_login_accepts_mixed_case_provider() -> None:
    from routes import auth as auth_routes

    auth_routes._csrf_states.clear()
    client = TestClient(_shared_app)
    try:
        with patch("routes.auth._get_client_credentials", return_value=("github-client", "github-secret")):
            response = client.get("/v1/auth/login/GitHub", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"].startswith("https://github.com/login/oauth/authorize?")
        assert "callback%2Fgithub" in response.headers["location"]
        assert len(auth_routes._csrf_states) == 1
        stored = next(iter(auth_routes._csrf_states.values()))
        assert stored["provider"] == "github"
    finally:
        client.close()
        auth_routes._csrf_states.clear()


def test_oauth_login_unsupported_provider_normalizes_detail() -> None:
    client = TestClient(_shared_app)
    try:
        response = client.get("/v1/auth/login/GiTaB", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported provider: gitab"


def test_oauth_callback_accepts_mixed_case_provider_before_state_check() -> None:
    from routes import auth as auth_routes

    auth_routes._csrf_states.clear()
    client = TestClient(_shared_app)
    try:
        response = client.get(
            "/v1/auth/callback/GitHub?code=fake-code&state=missing-state",
            follow_redirects=False,
        )
    finally:
        client.close()
        auth_routes._csrf_states.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired state parameter"


def test_oauth_callback_rejects_blank_code_before_csrf_state_pop() -> None:
    from routes import auth as auth_routes

    auth_routes._csrf_states.clear()
    created_at = time.time()
    auth_routes._csrf_states["state-123"] = {"provider": "github", "created_at": created_at}
    client = TestClient(_shared_app)
    try:
        with patch("routes.auth.httpx.AsyncClient") as mock_httpx:
            response = client.get(
                "/v1/auth/callback/GitHub?code=%20%20&state=state-123",
                follow_redirects=False,
            )
    finally:
        client.close()

    assert response.status_code == 400
    assert response.json()["detail"] == "code is required"
    assert auth_routes._csrf_states == {
        "state-123": {"provider": "github", "created_at": created_at}
    }
    mock_httpx.assert_not_called()
    auth_routes._csrf_states.clear()


def test_oauth_callback_rejects_blank_state_before_csrf_state_pop() -> None:
    from routes import auth as auth_routes

    auth_routes._csrf_states.clear()
    auth_routes._csrf_states[" "] = {"provider": "github", "created_at": time.time()}
    client = TestClient(_shared_app)
    try:
        with patch("routes.auth.httpx.AsyncClient") as mock_httpx:
            response = client.get(
                "/v1/auth/callback/GitHub?code=oauth-code&state=%20%20",
                follow_redirects=False,
            )
    finally:
        client.close()

    assert response.status_code == 400
    assert response.json()["detail"] == "state is required"
    assert " " in auth_routes._csrf_states
    mock_httpx.assert_not_called()
    auth_routes._csrf_states.clear()


def test_oauth_callback_mixed_case_provider_stays_canonical_through_profile_fetch_and_user_create() -> None:
    from routes import auth as auth_routes

    class DummyTokenResponse:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> dict[str, str]:
            return {"access_token": "github-token"}

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            return DummyTokenResponse()

    reset_user_store()
    reset_identity_store()
    user_store = UserStore(supabase_client=None)
    identity_store = AgentIdentityStore(supabase_client=None)
    fetch_profile = AsyncMock(
        return_value={
            "id": "github-user-123",
            "email": "mixedcase@example.com",
            "name": "Mixed Case",
            "avatar_url": "https://example.com/avatar.png",
        }
    )

    auth_routes._csrf_states.clear()
    auth_routes._csrf_states["state-123"] = {"provider": "github", "created_at": time.time()}

    client = TestClient(_shared_app)
    try:
        with (
            patch("routes.auth.get_user_store", return_value=user_store),
            patch("routes.auth.get_agent_identity_store", return_value=identity_store),
            patch("routes.auth.ensure_org_billing_bootstrap", new_callable=AsyncMock) as mock_bootstrap,
            patch("routes.auth._get_client_credentials", return_value=("github-client", "github-secret")),
            patch("routes.auth.httpx.AsyncClient", return_value=DummyClient()),
            patch("routes.auth._fetch_user_profile", fetch_profile),
            patch("routes.auth._issue_jwt", return_value="session-token"),
        ):
            response = client.get(
                "/v1/auth/callback/GitHub?code=oauth-code&state=state-123",
                follow_redirects=False,
            )
            created_user = _run(user_store.find_by_email("mixedcase@example.com"))

        assert response.status_code == 302
        assert response.headers["location"].startswith("https://rhumb.dev/dashboard?new=1#")
        fetch_profile.assert_awaited_once()
        assert fetch_profile.await_args.args[1] == "github"
        assert created_user is not None
        assert created_user.provider == "github"
        assert created_user.provider_id == "github-user-123"
        assert auth_routes._csrf_states == {}
        mock_bootstrap.assert_awaited_once()
    finally:
        client.close()
        auth_routes._csrf_states.clear()
        reset_user_store()
        reset_identity_store()


def test_request_code_returns_generic_success_for_existing_email() -> None:
    with _auth_email_harness() as env:
        existing_user = _run(
            env.user_store.create_user(
                email="existing@example.com",
                name="Existing User",
                provider="google",
                provider_id="google-existing",
            )
        )

        response = env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "existing@example.com"},
            headers={"x-forwarded-for": "203.0.113.8"},
        )
        latest_code = _run(env.otp_service.get_latest_code("existing@example.com"))

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert latest_code is not None
    assert latest_code.user_id == existing_user.user_id
    assert env.sender.calls[0]["email"] == "existing@example.com"


def test_request_code_returns_generic_success_when_otp_storage_fails() -> None:
    class BrokenOtpService:
        @staticmethod
        def normalize_email(email: str) -> str:
            return EmailOtpService.normalize_email(email)

        @staticmethod
        def derive_subnet(ip: str) -> str:
            return EmailOtpService.derive_subnet(ip)

        async def request_code(self, **_kwargs):
            raise RuntimeError('relation "email_verification_codes" does not exist')

    with _auth_email_harness() as env:
        with patch("routes.auth.get_email_otp_service", return_value=BrokenOtpService()):
            response = env.client.post(
                "/v1/auth/email/request-code",
                json={"email": "broken@example.com"},
                headers={
                    "origin": "https://rhumb.dev",
                    "x-forwarded-for": "203.0.113.9",
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "status": "ok",
            "message": "If the address can receive a sign-in code, it should arrive shortly.",
        },
        "error": None,
    }
    assert response.headers["access-control-allow-origin"] == "https://rhumb.dev"


def test_supabase_migration_track_includes_email_otp_schema() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    migration_path = repo_root / "supabase/migrations/0010_email_otp_user_bootstrap.sql"

    assert migration_path.exists()

    migration_sql = migration_path.read_text()
    assert "CREATE TABLE IF NOT EXISTS email_verification_codes" in migration_sql
    assert "ADD COLUMN IF NOT EXISTS signup_method" in migration_sql
    assert "ADD COLUMN IF NOT EXISTS email_verified_at" in migration_sql
    assert "ADD COLUMN IF NOT EXISTS credit_policy" in migration_sql


@pytest.mark.anyio
async def test_resend_sender_sets_user_agent_header() -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return DummyResponse()

    sender = ResendEmailOtpSender(
        api_key="re_test",
        from_address="Rhumb <no-reply@rhumb.dev>",
        base_url="https://api.resend.com",
    )

    with patch("services.email_otp.httpx.AsyncClient", return_value=DummyClient()):
        await sender.send_verification_code(
            email="agent@example.com",
            code="123456",
            ttl_minutes=10,
        )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"] == {
        "Authorization": "Bearer re_test",
        "Content-Type": "application/json",
        "User-Agent": "Rhumb/1.0",
    }
    assert captured["json"] == {
        "from": "Rhumb <no-reply@rhumb.dev>",
        "to": ["agent@example.com"],
        "subject": "Your Rhumb sign-in code",
        "text": (
            "Your Rhumb sign-in code is 123456.\n\n"
            "It expires in 10 minutes.\n\n"
            "If you did not request this, you can ignore this email."
        ),
    }


@pytest.mark.anyio
async def test_request_code_enforces_email_ip_and_subnet_limits() -> None:
    sender = RecordingEmailSender()
    service = EmailOtpService(
        supabase_client=None,
        email_sender=sender,
        resend_cooldown_seconds=0,
        email_hourly_limit=1,
        ip_hourly_limit=2,
        subnet_hourly_limit=3,
    )

    first = await service.request_code(
        email="one@example.com",
        sent_ip="198.51.100.10",
        sent_subnet="198.51.100.0/24",
    )
    second_same_email = await service.request_code(
        email="one@example.com",
        sent_ip="198.51.100.10",
        sent_subnet="198.51.100.0/24",
    )
    second_ip = await service.request_code(
        email="two@example.com",
        sent_ip="198.51.100.10",
        sent_subnet="198.51.100.0/24",
    )
    third_ip = await service.request_code(
        email="three@example.com",
        sent_ip="198.51.100.10",
        sent_subnet="198.51.100.0/24",
    )
    third_subnet = await service.request_code(
        email="four@example.com",
        sent_ip="198.51.100.11",
        sent_subnet="198.51.100.0/24",
    )
    fourth_subnet = await service.request_code(
        email="five@example.com",
        sent_ip="198.51.100.12",
        sent_subnet="198.51.100.0/24",
    )

    assert first.accepted is True
    assert second_same_email.accepted is False
    assert second_ip.accepted is True
    assert third_ip.accepted is False
    assert third_subnet.accepted is True
    assert fourth_subnet.accepted is False
    assert len(sender.calls) == 3


def test_verify_code_creates_email_signup_user_and_zero_credit_bootstrap() -> None:
    with _auth_email_harness() as env:
        request_response = env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "snowy@example.com"},
            headers={"x-forwarded-for": "203.0.113.11"},
        )
        code = str(env.sender.calls[-1]["code"])

        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={
                "email": "snowy@example.com",
                "code": code,
                "device_label": "Snowy",
            },
            headers={"x-forwarded-for": "203.0.113.11"},
        )

        created_user = _run(env.user_store.find_by_email("snowy@example.com"))
        created_agent = _run(env.identity_store.get_agent(created_user.default_agent_id))
        latest_code = _run(env.otp_service.get_latest_code("snowy@example.com"))

    assert request_response.status_code == 200
    assert verify_response.status_code == 200
    payload = verify_response.json()["data"]
    assert payload["session_token"]
    assert payload["new_user"] is True
    assert payload["api_key"].startswith("rhumb_")
    assert payload["user"]["provider"] == EMAIL_AUTH_PROVIDER
    assert payload["user"]["signup_method"] == EMAIL_OTP_SIGNUP_METHOD
    assert payload["user"]["credit_policy"] == EMAIL_NO_TRIAL_CREDIT_POLICY

    assert created_user is not None
    assert created_user.provider_id == build_email_provider_id("snowy@example.com")
    assert created_user.email_verified_at is not None
    assert created_user.signup_ip == "203.0.113.11"
    assert created_user.signup_subnet == "203.0.113.0/24"
    assert created_agent is not None
    assert latest_code is not None
    assert latest_code.used_at is not None
    assert latest_code.user_id == created_user.user_id

    env.bootstrap.assert_awaited_once_with(
        created_user.organization_id,
        email="snowy@example.com",
        name="Snowy",
        signup_method=EMAIL_OTP_SIGNUP_METHOD,
        credit_policy=EMAIL_NO_TRIAL_CREDIT_POLICY,
        starter_credits_cents=0,
    )


def test_verify_code_reuses_existing_email_user_when_safe() -> None:
    with _auth_email_harness() as env:
        agent_id, _api_key = _run(
            env.identity_store.register_agent(
                name="Existing Agent",
                organization_id="org_existing",
            )
        )
        existing_user = _run(
            env.user_store.create_user(
                email="existing@example.com",
                name="Existing User",
                provider="google",
                provider_id="google-existing",
                organization_id="org_existing",
                default_agent_id=agent_id,
                signup_method=OAUTH_SIGNUP_METHOD,
            )
        )

        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "existing@example.com"},
            headers={"x-forwarded-for": "203.0.113.12"},
        )
        code = str(env.sender.calls[-1]["code"])

        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "existing@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.12"},
        )

        fetched_user = _run(env.user_store.find_by_email("existing@example.com"))

    assert verify_response.status_code == 200
    assert verify_response.json()["data"]["new_user"] is False
    assert verify_response.json()["data"]["api_key"] is None
    assert fetched_user is not None
    assert fetched_user.user_id == existing_user.user_id
    assert fetched_user.provider == "google"
    assert fetched_user.organization_id == "org_existing"
    assert fetched_user.default_agent_id == agent_id
    env.bootstrap.assert_awaited_once()
    assert "starter_credits_cents" not in env.bootstrap.await_args.kwargs


def test_email_signup_can_issue_api_key_after_verification() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "rotate@example.com"},
            headers={"x-forwarded-for": "203.0.113.13"},
        )
        code = str(env.sender.calls[-1]["code"])

        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "rotate@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.13"},
        )
        rotate_response = env.client.post(
            "/v1/auth/rotate-key",
            cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
        )

    assert verify_response.status_code == 200
    assert rotate_response.status_code == 200
    assert rotate_response.json()["api_key"].startswith("rhumb_")


def test_invalid_code_increments_attempts_and_locks_after_limit() -> None:
    with _auth_email_harness(max_attempts=2) as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "lockout@example.com"},
            headers={"x-forwarded-for": "203.0.113.14"},
        )

        first = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "lockout@example.com", "code": "111111"},
            headers={"x-forwarded-for": "203.0.113.14"},
        )
        after_first = _run(env.otp_service.get_latest_code("lockout@example.com"))

        second = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "lockout@example.com", "code": "222222"},
            headers={"x-forwarded-for": "203.0.113.14"},
        )
        after_second = _run(env.otp_service.get_latest_code("lockout@example.com"))

        third = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "lockout@example.com", "code": "333333"},
            headers={"x-forwarded-for": "203.0.113.14"},
        )
        after_third = _run(env.otp_service.get_latest_code("lockout@example.com"))

    assert first.status_code == 400
    assert after_first is not None
    assert after_first.attempt_count == 1
    assert after_first.invalidated_at is None

    assert second.status_code == 400
    assert after_second is not None
    assert after_second.attempt_count == 2
    assert after_second.invalidated_at is not None

    assert third.status_code == 400
    assert after_third is not None
    assert after_third.attempt_count == 2


def test_expired_code_is_rejected() -> None:
    with _auth_email_harness(ttl_seconds=0) as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "expired@example.com"},
            headers={"x-forwarded-for": "203.0.113.15"},
        )
        code = str(env.sender.calls[-1]["code"])

        response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "expired@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.15"},
        )
        latest_code = _run(env.otp_service.get_latest_code("expired@example.com"))

    assert response.status_code == 400
    assert latest_code is not None
    assert latest_code.invalidated_at is not None


class _FakeUsageAnalytics:
    async def get_usage_summary(self, agent_id: str, days: int) -> dict:
        assert agent_id
        if days == 1:
            return {"total_calls": 2, "services": {}}
        return {
            "total_calls": 5,
            "services": {
                "brave-search": {"calls": 2},
                "brave-search-api": {"calls": 1},
                "pdl": {"calls": 2},
            },
        }

    async def get_recent_events(self, agent_id: str, limit: int = 10) -> list[dict[str, object]]:
        assert agent_id
        assert limit == 10
        return [
            {
                "service": "brave-search",
                "result": "success",
                "latency_ms": 123,
                "created_at": "2026-04-17T22:00:00Z",
            },
            {
                "service": "pdl",
                "result": "error",
                "latency_ms": 456,
                "created_at": "2026-04-17T22:01:00Z",
            },
        ]


def test_me_usage_canonicalizes_alias_backed_service_ids() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "usage@example.com"},
            headers={"x-forwarded-for": "203.0.113.21"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "usage@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.21"},
        )

        with patch(
            "services.agent_usage_analytics.get_usage_analytics",
            return_value=_FakeUsageAnalytics(),
        ):
            usage_response = env.client.get(
                "/v1/auth/me/usage",
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert usage_response.status_code == 200
    assert usage_response.json() == {
        "total_calls": 5,
        "calls_this_month": 5,
        "calls_today": 2,
        "calls_by_service": {
            "brave-search-api": 3,
            "people-data-labs": 2,
        },
        "recent_calls": [
            {
                "service": "brave-search-api",
                "result": "success",
                "latency_ms": 123,
                "timestamp": "2026-04-17T22:00:00Z",
            },
            {
                "service": "people-data-labs",
                "result": "error",
                "latency_ms": 456,
                "timestamp": "2026-04-17T22:01:00Z",
            },
        ],
    }


def test_me_billing_uses_credit_ledger_and_saved_payment_method_truth() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "billing@example.com"},
            headers={"x-forwarded-for": "203.0.113.22"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "billing@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.22"},
        )

        with patch(
            "routes._supabase.supabase_fetch",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.side_effect = [
                [{
                    "balance_usd_cents": 2500,
                    "reserved_usd_cents": 0,
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1000,
                    "auto_reload_amount_cents": 5000,
                    "stripe_payment_method_id": "pm_saved_123",
                }],
                [{
                    "event_type": "credit_added",
                    "amount_usd_cents": 2500,
                    "description": "Credit purchase via Stripe Checkout ($25.00)",
                    "created_at": "2026-04-21T20:00:00Z",
                }],
            ]

            billing_response = env.client.get(
                "/v1/auth/me/billing",
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert billing_response.status_code == 200
    assert billing_response.json() == {
        "balance_usd": 25.0,
        "plan": "prepaid",
        "has_payment_method": True,
        "auto_reload_enabled": True,
        "auto_reload_threshold_usd": 10.0,
        "auto_reload_amount_usd": 50.0,
        "recent_transactions": [
            {
                "type": "credit_added",
                "amount_usd": 25.0,
                "description": "Credit purchase via Stripe Checkout ($25.00)",
                "timestamp": "2026-04-21T20:00:00Z",
            }
        ],
    }
    assert "credit_ledger?org_id=eq." in mock_fetch.call_args_list[1].args[0]


def test_me_billing_checkout_creates_dashboard_checkout_session() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "checkout@example.com"},
            headers={"x-forwarded-for": "203.0.113.23"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "checkout@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.23"},
        )

        with patch(
            "routes.auth.create_checkout_session",
            new_callable=AsyncMock,
            return_value={
                "checkout_url": "https://checkout.stripe.com/pay/cs_test_dashboard",
                "session_id": "cs_test_dashboard",
            },
        ) as mock_checkout:
            checkout_response = env.client.post(
                "/v1/auth/me/billing/checkout",
                json={"amount_usd": 25.0},
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert checkout_response.status_code == 200
    assert checkout_response.json()["session_id"] == "cs_test_dashboard"
    assert mock_checkout.await_args.kwargs["amount_cents"] == 2500
    assert mock_checkout.await_args.kwargs["success_url"].endswith(
        "/dashboard?checkout=success&session_id={CHECKOUT_SESSION_ID}"
    )
    assert mock_checkout.await_args.kwargs["cancel_url"].endswith("/dashboard?checkout=cancel")


def test_me_billing_checkout_confirm_calls_stripe_confirm_service() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "checkout-confirm@example.com"},
            headers={"x-forwarded-for": "203.0.113.23"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "checkout-confirm@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.23"},
        )

        user = _run(env.user_store.find_by_email("checkout-confirm@example.com"))
        assert user is not None
        org_id = user.organization_id

        with patch(
            "routes.auth.confirm_checkout_session_detailed",
            new_callable=AsyncMock,
            return_value={"processed": True, "reason": "credited"},
        ) as mock_confirm:
            resp = env.client.post(
                "/v1/auth/me/billing/checkout/confirm",
                json={"session_id": "cs_test_confirm"},
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert resp.status_code == 200
    assert resp.json()["processed"] is True
    assert mock_confirm.await_args.kwargs["expected_org_id"] == org_id


def test_me_billing_checkout_rejects_invalid_amount_before_session_lookup() -> None:
    with _auth_email_harness() as env:
        with patch("routes.auth._require_session", new_callable=AsyncMock) as mock_session:
            response = env.client.post(
                "/v1/auth/me/billing/checkout",
                json={"amount_usd": 1.0},
            )

    assert response.status_code == 400
    assert "amount_usd must be between" in response.json()["detail"]
    mock_session.assert_not_awaited()


def test_me_billing_checkout_confirm_rejects_blank_session_id_before_session_lookup() -> None:
    with _auth_email_harness() as env:
        with patch("routes.auth._require_session", new_callable=AsyncMock) as mock_session:
            response = env.client.post(
                "/v1/auth/me/billing/checkout/confirm",
                json={"session_id": "   "},
            )

    assert response.status_code == 400
    assert response.json()["detail"] == "session_id is required"
    mock_session.assert_not_awaited()


def test_me_billing_auto_reload_rejects_invalid_config_before_session_lookup() -> None:
    with _auth_email_harness() as env:
        with patch("routes.auth._require_session", new_callable=AsyncMock) as mock_session:
            threshold_response = env.client.put(
                "/v1/auth/me/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 0, "amount_usd": 50.0},
            )
            amount_response = env.client.put(
                "/v1/auth/me/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 10.0, "amount_usd": 1.0},
            )

    assert threshold_response.status_code == 400
    assert threshold_response.json()["detail"] == "threshold_usd must be > 0 when auto-reload is enabled"
    assert amount_response.status_code == 400
    assert "amount_usd must be between" in amount_response.json()["detail"]
    mock_session.assert_not_awaited()


def test_me_billing_auto_reload_requires_saved_payment_method() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "autoreload-missing@example.com"},
            headers={"x-forwarded-for": "203.0.113.24"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "autoreload-missing@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.24"},
        )

        with patch(
            "routes._supabase.supabase_fetch",
            new_callable=AsyncMock,
            return_value=[{"stripe_payment_method_id": None}],
        ):
            response = env.client.put(
                "/v1/auth/me/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 10.0, "amount_usd": 50.0},
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert response.status_code == 400
    assert "saved payment method" in response.json()["detail"]


def test_me_billing_auto_reload_updates_org_credit_config() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "autoreload@example.com"},
            headers={"x-forwarded-for": "203.0.113.25"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "autoreload@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.25"},
        )

        with patch(
            "routes._supabase.supabase_fetch",
            new_callable=AsyncMock,
            return_value=[{"stripe_payment_method_id": "pm_saved_123"}],
        ) as mock_fetch, patch(
            "routes._supabase.supabase_patch",
            new_callable=AsyncMock,
            return_value=[
                {
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1500,
                    "auto_reload_amount_cents": 5000,
                }
            ],
        ) as mock_patch:
            response = env.client.put(
                "/v1/auth/me/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 15.0, "amount_usd": 50.0},
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert response.status_code == 200
    assert response.json() == {
        "auto_reload_enabled": True,
        "auto_reload_threshold_usd": 15.0,
        "auto_reload_amount_usd": 50.0,
    }
    assert "org_credits?org_id=eq." in mock_fetch.call_args.args[0]
    assert mock_patch.call_args.args[0].startswith("org_credits?org_id=eq.")
    assert mock_patch.call_args.args[1] == {
        "auto_reload_enabled": True,
        "auto_reload_threshold_cents": 1500,
        "auto_reload_amount_cents": 5000,
    }


def test_me_agents_can_create_and_list_capped_secondary_keys() -> None:
    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "agents@example.com"},
            headers={"x-forwarded-for": "203.0.113.26"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "agents@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.26"},
        )

        created_user = _run(env.user_store.find_by_email("agents@example.com"))
        assert created_user is not None

        with patch(
            "routes._supabase.supabase_insert_returning",
            new_callable=AsyncMock,
            return_value={
                "agent_id": "agent-secondary",
                "budget_usd": 12.5,
                "spent_usd": 0,
                "period": "monthly",
                "hard_limit": True,
            },
        ) as mock_insert:
            create_response = env.client.post(
                "/v1/auth/me/agents",
                json={
                    "name": "Friend Agent",
                    "description": "Key for a friend",
                    "budget_usd": 12.5,
                    "period": "monthly",
                    "hard_limit": True,
                    "rate_limit_qpm": 15,
                },
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

        assert create_response.status_code == 200
        created = create_response.json()
        assert created["agent_id"]
        assert created["api_key"].startswith("rhumb_")
        assert created["rate_limit_qpm"] == 15
        assert created["budget"]["budget_usd"] == 12.5
        assert created["budget"]["period"] == "monthly"
        assert mock_insert.await_args.args[0] == "agent_budgets"
        assert mock_insert.await_args.args[1]["budget_usd"] == 12.5

        secondary_agent = _run(env.identity_store.get_agent(created["agent_id"]))
        assert secondary_agent is not None
        assert secondary_agent.organization_id == created_user.organization_id
        assert secondary_agent.rate_limit_qpm == 15
        assert "secondary" in (secondary_agent.tags or [])

        async def _budget_side_effect(path: str):
            if path.startswith("agent_budgets?agent_id=eq.") and created["agent_id"] in path:
                return [
                    {
                        "budget_usd": 12.5,
                        "spent_usd": 0,
                        "period": "monthly",
                        "hard_limit": True,
                        "alert_threshold_pct": 80,
                        "alert_fired": False,
                    }
                ]
            return []

        with patch(
            "routes._supabase.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_budget_side_effect,
        ):
            list_response = env.client.get(
                "/v1/auth/me/agents",
                cookies={"rhumb_session": verify_response.json()["data"]["session_token"]},
            )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert "agents" in payload
    assert any(item["agent_id"] == created["agent_id"] for item in payload["agents"])


def test_onboarding_journey_smoke_for_session_auth_routes() -> None:
    """A thin regression smoke for the self-serve onboarding control-plane."""

    with _auth_email_harness() as env:
        env.client.post(
            "/v1/auth/email/request-code",
            json={"email": "journey@example.com"},
            headers={"x-forwarded-for": "203.0.113.27"},
        )
        code = str(env.sender.calls[-1]["code"])
        verify_response = env.client.post(
            "/v1/auth/email/verify-code",
            json={"email": "journey@example.com", "code": code},
            headers={"x-forwarded-for": "203.0.113.27"},
        )
        session_token = verify_response.json()["data"]["session_token"]

        secondary_agent_id: str | None = None

        async def _supabase_fetch_side_effect(path: str):
            nonlocal secondary_agent_id
            if path.startswith("org_credits?org_id=eq.") and "stripe_payment_method_id" in path:
                return [
                    {
                        "balance_usd_cents": 2500,
                        "reserved_usd_cents": 0,
                        "auto_reload_enabled": False,
                        "auto_reload_threshold_cents": None,
                        "auto_reload_amount_cents": None,
                        "stripe_payment_method_id": "pm_saved_123",
                    }
                ]
            if path.startswith("credit_ledger?org_id=eq."):
                return [
                    {
                        "event_type": "credit_added",
                        "amount_usd_cents": 2500,
                        "description": "Credit purchase via Stripe Checkout ($25.00)",
                        "created_at": "2026-04-21T20:00:00Z",
                    }
                ]
            if path.startswith("agent_budgets?agent_id=eq.") and secondary_agent_id and secondary_agent_id in path:
                return [
                    {
                        "budget_usd": 10.0,
                        "spent_usd": 0.0,
                        "period": "monthly",
                        "hard_limit": True,
                        "alert_threshold_pct": 80,
                        "alert_fired": False,
                    }
                ]
            return []

        with patch(
            "routes._supabase.supabase_fetch",
            new_callable=AsyncMock,
            side_effect=_supabase_fetch_side_effect,
        ), patch(
            "routes._supabase.supabase_patch",
            new_callable=AsyncMock,
            return_value=[
                {
                    "auto_reload_enabled": True,
                    "auto_reload_threshold_cents": 1000,
                    "auto_reload_amount_cents": 5000,
                }
            ],
        ), patch(
            "routes._supabase.supabase_insert_returning",
            new_callable=AsyncMock,
            return_value={
                "budget_usd": 10.0,
                "spent_usd": 0.0,
                "period": "monthly",
                "hard_limit": True,
            },
        ), patch(
            "routes.auth.create_checkout_session",
            new_callable=AsyncMock,
            return_value={
                "checkout_url": "https://checkout.stripe.com/pay/cs_test_dashboard",
                "session_id": "cs_test_dashboard",
            },
        ):
            me_response = env.client.get(
                "/v1/auth/me",
                cookies={"rhumb_session": session_token},
            )
            assert me_response.status_code == 200
            assert me_response.json()["api_key_prefix"]

            billing_response = env.client.get(
                "/v1/auth/me/billing",
                cookies={"rhumb_session": session_token},
            )
            assert billing_response.status_code == 200
            assert billing_response.json()["balance_usd"] == 25.0
            assert billing_response.json()["has_payment_method"] is True

            checkout_response = env.client.post(
                "/v1/auth/me/billing/checkout",
                json={"amount_usd": 25.0},
                cookies={"rhumb_session": session_token},
            )
            assert checkout_response.status_code == 200
            assert checkout_response.json()["session_id"] == "cs_test_dashboard"

            auto_reload_response = env.client.put(
                "/v1/auth/me/billing/auto-reload",
                json={"enabled": True, "threshold_usd": 10.0, "amount_usd": 50.0},
                cookies={"rhumb_session": session_token},
            )
            assert auto_reload_response.status_code == 200
            assert auto_reload_response.json()["auto_reload_enabled"] is True

            create_key_response = env.client.post(
                "/v1/auth/me/agents",
                json={
                    "name": "Friend Agent",
                    "budget_usd": 10.0,
                    "period": "monthly",
                    "hard_limit": True,
                    "rate_limit_qpm": 20,
                },
                cookies={"rhumb_session": session_token},
            )
            assert create_key_response.status_code == 200
            secondary_agent_id = create_key_response.json()["agent_id"]
            assert create_key_response.json()["api_key"].startswith("rhumb_")

            list_keys_response = env.client.get(
                "/v1/auth/me/agents",
                cookies={"rhumb_session": session_token},
            )
            assert list_keys_response.status_code == 200
            assert any(
                row["agent_id"] == secondary_agent_id
                for row in list_keys_response.json().get("agents", [])
            )
