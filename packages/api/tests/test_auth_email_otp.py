"""Focused tests for the email OTP auth slice."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
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
