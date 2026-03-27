"""Email OTP issuance, verification, and minimal transactional delivery."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional, Protocol

import httpx
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)

EMAIL_OTP_TTL_SECONDS = 10 * 60
EMAIL_OTP_RESEND_COOLDOWN_SECONDS = 60
EMAIL_OTP_MAX_ATTEMPTS = 5
EMAIL_OTP_EMAIL_HOURLY_LIMIT = 3
EMAIL_OTP_IP_HOURLY_LIMIT = 10
EMAIL_OTP_SUBNET_HOURLY_LIMIT = 30
EMAIL_OTP_SUBJECT = "Your Rhumb sign-in code"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def normalize_email(email: str) -> str:
    """Normalize an email for storage and lookup."""
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("A valid email address is required")
    return normalized


def derive_request_ip(raw_ip: str | None) -> str:
    """Return a normalized request IP, or an empty string if unavailable."""
    if not raw_ip:
        return ""

    candidate = raw_ip.split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return ""


def derive_request_subnet(ip: str) -> str:
    """Return a coarse subnet key for abuse controls."""
    if not ip:
        return ""

    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ""

    if parsed.version == 4:
        network = ipaddress.ip_network(f"{parsed}/24", strict=False)
    else:
        network = ipaddress.ip_network(f"{parsed}/64", strict=False)
    return str(network)


def _otp_hash_secret() -> str:
    secret = settings.auth_jwt_secret or settings.rhumb_admin_secret
    if not secret:
        raise RuntimeError(
            "No OTP hash secret configured "
            "(set AUTH_JWT_SECRET or RHUMB_ADMIN_SECRET)"
        )
    return secret


def _hash_code(email: str, code: str) -> str:
    return hmac.new(
        _otp_hash_secret().encode("utf-8"),
        f"{email}:{code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class EmailVerificationCodeSchema(BaseModel):
    """Stored OTP code metadata."""

    id: str = Field(..., description="UUID verification code identifier")
    email: str = Field(..., description="Normalized recipient email")
    user_id: Optional[str] = Field(default=None, description="Linked user ID, when known")
    code_hash: str = Field(..., description="HMAC-SHA256 hash of the OTP code")
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime = Field(...)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=EMAIL_OTP_MAX_ATTEMPTS)
    sent_ip: str = Field(default="")
    sent_subnet: str = Field(default="")
    used_at: Optional[datetime] = Field(default=None)
    invalidated_at: Optional[datetime] = Field(default=None)


@dataclass(frozen=True)
class EmailOtpRequestResult:
    """Outcome of a request-code call."""

    accepted: bool
    reason: str


@dataclass(frozen=True)
class EmailOtpVerifyResult:
    """Outcome of a verify-code call."""

    verified: bool
    reason: str
    code_id: str | None = None


class EmailOtpSender(Protocol):
    """Minimal sender interface for OTP delivery."""

    async def send_verification_code(self, *, email: str, code: str, ttl_minutes: int) -> None:
        """Deliver the verification code."""


class LoggingEmailOtpSender:
    """Fallback sender that logs OTP issuance when no provider is configured."""

    async def send_verification_code(self, *, email: str, code: str, ttl_minutes: int) -> None:
        logger.info(
            "Email OTP generated for %s (ttl_minutes=%s, code=%s); "
            "no transactional provider configured",
            email,
            ttl_minutes,
            code,
        )


class ResendEmailOtpSender:
    """Send OTP emails through Resend."""

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        base_url: str,
    ) -> None:
        self._api_key = api_key
        self._from_address = from_address
        self._base_url = base_url.rstrip("/")

    async def send_verification_code(self, *, email: str, code: str, ttl_minutes: int) -> None:
        payload = {
            "from": self._from_address,
            "to": [email],
            "subject": EMAIL_OTP_SUBJECT,
            "text": (
                f"Your Rhumb sign-in code is {code}.\n\n"
                f"It expires in {ttl_minutes} minutes.\n\n"
                "If you did not request this, you can ignore this email."
            ),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/emails",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Rhumb/1.0",
                },
                json=payload,
            )
            response.raise_for_status()


def build_email_otp_sender() -> EmailOtpSender:
    """Return the configured OTP sender."""
    if settings.auth_email_resend_api_key:
        return ResendEmailOtpSender(
            api_key=settings.auth_email_resend_api_key,
            from_address=settings.auth_email_from,
            base_url=settings.auth_email_resend_base_url,
        )
    return LoggingEmailOtpSender()


class EmailOtpService:
    """Manage OTP code storage, abuse controls, and delivery."""

    def __init__(
        self,
        supabase_client: Any = None,
        *,
        email_sender: EmailOtpSender | None = None,
        ttl_seconds: int = EMAIL_OTP_TTL_SECONDS,
        resend_cooldown_seconds: int = EMAIL_OTP_RESEND_COOLDOWN_SECONDS,
        max_attempts: int = EMAIL_OTP_MAX_ATTEMPTS,
        email_hourly_limit: int = EMAIL_OTP_EMAIL_HOURLY_LIMIT,
        ip_hourly_limit: int = EMAIL_OTP_IP_HOURLY_LIMIT,
        subnet_hourly_limit: int = EMAIL_OTP_SUBNET_HOURLY_LIMIT,
    ) -> None:
        self.supabase = supabase_client
        self.email_sender = email_sender or build_email_otp_sender()
        self.ttl_seconds = ttl_seconds
        self.resend_cooldown_seconds = resend_cooldown_seconds
        self.max_attempts = max_attempts
        self.email_hourly_limit = email_hourly_limit
        self.ip_hourly_limit = ip_hourly_limit
        self.subnet_hourly_limit = subnet_hourly_limit
        self._mem_codes: Dict[str, Dict[str, Any]] = {}

    async def request_code(
        self,
        *,
        email: str,
        sent_ip: str = "",
        sent_subnet: str = "",
        user_id: str | None = None,
        request_ip: str | None = None,
        request_subnet: str | None = None,
    ) -> EmailOtpRequestResult:
        """Issue and deliver an OTP code unless abuse controls block it."""
        if request_ip is not None:
            sent_ip = request_ip
        if request_subnet is not None:
            sent_subnet = request_subnet
        normalized_email = normalize_email(email)
        now = _utcnow()

        if await self._is_throttled(normalized_email, sent_ip, sent_subnet, now):
            return EmailOtpRequestResult(accepted=False, reason="rate_limited")

        code = _generate_code()
        record = {
            "id": str(uuid.uuid4()),
            "email": normalized_email,
            "user_id": user_id,
            "code_hash": _hash_code(normalized_email, code),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.ttl_seconds)).isoformat(),
            "attempt_count": 0,
            "max_attempts": self.max_attempts,
            "sent_ip": sent_ip,
            "sent_subnet": sent_subnet,
            "used_at": None,
            "invalidated_at": None,
        }

        await self._invalidate_active_codes(normalized_email, invalidated_at=now)
        await self._insert_code(record)

        try:
            await self.email_sender.send_verification_code(
                email=normalized_email,
                code=code,
                ttl_minutes=max(1, self.ttl_seconds // 60),
            )
        except Exception:
            logger.exception("Failed to deliver OTP email to %s", normalized_email)
            await self._update_code(record["id"], invalidated_at=now.isoformat())
            return EmailOtpRequestResult(accepted=False, reason="delivery_failed")

        return EmailOtpRequestResult(accepted=True, reason="sent")

    async def verify_code(self, *, email: str, code: str) -> EmailOtpVerifyResult:
        """Verify an OTP code, applying expiry and attempt caps."""
        normalized_email = normalize_email(email)
        active = await self._get_active_code(normalized_email)
        if active is None:
            return EmailOtpVerifyResult(verified=False, reason="invalid")

        now = _utcnow()
        if active.expires_at <= now:
            await self._update_code(active.id, invalidated_at=now.isoformat())
            return EmailOtpVerifyResult(verified=False, reason="expired", code_id=active.id)

        if active.attempt_count >= active.max_attempts:
            await self._update_code(active.id, invalidated_at=now.isoformat())
            return EmailOtpVerifyResult(verified=False, reason="exhausted", code_id=active.id)

        if not hmac.compare_digest(active.code_hash, _hash_code(normalized_email, code.strip())):
            attempts = active.attempt_count + 1
            update: Dict[str, Any] = {"attempt_count": attempts}
            if attempts >= active.max_attempts:
                update["invalidated_at"] = now.isoformat()
            await self._update_code(active.id, **update)
            return EmailOtpVerifyResult(
                verified=False,
                reason="exhausted" if attempts >= active.max_attempts else "invalid",
                code_id=active.id,
            )

        await self._update_code(active.id, used_at=now.isoformat())
        return EmailOtpVerifyResult(verified=True, reason="verified", code_id=active.id)

    async def get_latest_code(self, email: str) -> EmailVerificationCodeSchema | None:
        """Return the latest code row for tests and diagnostics."""
        normalized_email = normalize_email(email)
        rows = await self._list_codes_for_email(normalized_email)
        if not rows:
            return None
        return rows[0]

    async def attach_verified_user(self, code_id: str, user_id: str) -> None:
        """Link a verified OTP record to the user that completed verification."""
        await self._update_code(code_id, user_id=user_id)

    async def _is_throttled(
        self,
        email: str,
        sent_ip: str,
        sent_subnet: str,
        now: datetime,
    ) -> bool:
        cooldown_cutoff = now - timedelta(seconds=self.resend_cooldown_seconds)
        latest_for_email = await self._get_latest_for_email(email)
        if latest_for_email is not None and latest_for_email.created_at >= cooldown_cutoff:
            return True

        hourly_cutoff = now - timedelta(hours=1)
        if (
            len(await self._list_codes_by_filter(email=email, created_after=hourly_cutoff))
            >= self.email_hourly_limit
        ):
            return True
        if sent_ip and (
            len(await self._list_codes_by_filter(sent_ip=sent_ip, created_after=hourly_cutoff))
            >= self.ip_hourly_limit
        ):
            return True
        if sent_subnet and (
            len(
                await self._list_codes_by_filter(
                    sent_subnet=sent_subnet,
                    created_after=hourly_cutoff,
                )
            )
            >= self.subnet_hourly_limit
        ):
            return True
        return False

    async def _get_latest_for_email(self, email: str) -> EmailVerificationCodeSchema | None:
        rows = await self._list_codes_for_email(email)
        if not rows:
            return None
        return rows[0]

    async def _get_active_code(self, email: str) -> EmailVerificationCodeSchema | None:
        rows = await self._list_codes_for_email(email)
        for row in rows:
            if row.used_at is None and row.invalidated_at is None:
                return row
        return None

    async def _invalidate_active_codes(self, email: str, *, invalidated_at: datetime) -> None:
        rows = await self._list_codes_for_email(email)
        for row in rows:
            if row.used_at is None and row.invalidated_at is None:
                await self._update_code(row.id, invalidated_at=invalidated_at.isoformat())

    async def _list_codes_for_email(self, email: str) -> list[EmailVerificationCodeSchema]:
        return await self._list_codes_by_filter(email=email, limit=20)

    async def _list_codes_by_filter(
        self,
        *,
        email: str | None = None,
        sent_ip: str | None = None,
        sent_subnet: str | None = None,
        created_after: datetime | None = None,
        limit: int = 100,
    ) -> list[EmailVerificationCodeSchema]:
        rows: list[dict[str, Any]]

        if self.supabase is not None:
            query = self.supabase.table("email_verification_codes").select("*")
            if email is not None:
                query = query.eq("email", email)
            if sent_ip is not None:
                query = query.eq("sent_ip", sent_ip)
            if sent_subnet is not None:
                query = query.eq("sent_subnet", sent_subnet)
            if created_after is not None:
                query = query.gte("created_at", created_after.isoformat())
            response = await query.order("created_at", desc=True).limit(limit).execute()
            rows = response.data or []
        else:
            rows = []
            for row in self._mem_codes.values():
                if email is not None and row["email"] != email:
                    continue
                if sent_ip is not None and row.get("sent_ip", "") != sent_ip:
                    continue
                if sent_subnet is not None and row.get("sent_subnet", "") != sent_subnet:
                    continue
                if (
                    created_after is not None
                    and datetime.fromisoformat(row["created_at"]) < created_after
                ):
                    continue
                rows.append(row)
            rows.sort(key=lambda item: item["created_at"], reverse=True)
            rows = rows[:limit]

        return [self._row_to_schema(row) for row in rows]

    async def _insert_code(self, row: dict[str, Any]) -> None:
        if self.supabase is not None:
            await self.supabase.table("email_verification_codes").insert(row).execute()
        else:
            self._mem_codes[row["id"]] = row

    async def _update_code(self, code_id: str, **fields: Any) -> None:
        if self.supabase is not None:
            await (
                self.supabase.table("email_verification_codes")
                .update(fields)
                .eq("id", code_id)
                .execute()
            )
        else:
            existing = self._mem_codes.get(code_id)
            if existing is not None:
                existing.update(fields)

    @staticmethod
    def _row_to_schema(row: dict[str, Any]) -> EmailVerificationCodeSchema:
        return EmailVerificationCodeSchema(
            id=row["id"],
            email=row["email"],
            user_id=row.get("user_id"),
            code_hash=row["code_hash"],
            created_at=row.get("created_at", _utcnow()),
            expires_at=row["expires_at"],
            attempt_count=row.get("attempt_count", 0),
            max_attempts=row.get("max_attempts", EMAIL_OTP_MAX_ATTEMPTS),
            sent_ip=row.get("sent_ip", ""),
            sent_subnet=row.get("sent_subnet", ""),
            used_at=row.get("used_at"),
            invalidated_at=row.get("invalidated_at"),
        )


_email_otp_service: Optional[EmailOtpService] = None


def get_email_otp_service(supabase_client: Any = None) -> EmailOtpService:
    """Return the shared OTP service singleton."""
    global _email_otp_service
    if _email_otp_service is None:
        _email_otp_service = EmailOtpService(supabase_client)
    return _email_otp_service


def reset_email_otp_service() -> None:
    """Reset the shared OTP service singleton."""
    global _email_otp_service
    _email_otp_service = None


class EmailOTPService(EmailOtpService):
    """Compatibility wrapper for the groundwork auth wiring."""

    @staticmethod
    def normalize_email(email: str) -> str:
        return normalize_email(email)

    @staticmethod
    def derive_subnet(ip: str) -> str:
        return derive_request_subnet(ip)
