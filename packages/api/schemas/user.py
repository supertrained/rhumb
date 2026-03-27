"""User identity schema for dashboard and agent-facing auth users.

Agents still have runtime identities in ``agent_identity.py``. This
schema represents the owning human or agent operator account in the
shared ``users`` table, regardless of whether it was created by OAuth
or email OTP verification.

A user owns one default organization and one default agent, created
automatically on first successful auth.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


OAUTH_SIGNUP_METHOD = "oauth"
EMAIL_OTP_SIGNUP_METHOD = "email_otp"

OAUTH_TRIAL_CREDIT_POLICY = "oauth_trial"
EMAIL_NO_TRIAL_CREDIT_POLICY = "email_no_trial"

EMAIL_AUTH_PROVIDER = "email"


def build_email_provider_id(email: str) -> str:
    """Return the sentinel provider ID used for email-auth users."""
    return f"{EMAIL_AUTH_PROVIDER}:{email.strip().lower()}"


# ── Schema ───────────────────────────────────────────────────────────


class UserSchema(BaseModel):
    """Unified user record mirroring the shared ``users`` table."""

    user_id: str = Field(..., description="UUID user identifier")
    email: str = Field(..., description="Primary user email")
    name: str = Field(default="", description="Display name")
    avatar_url: str = Field(default="", description="Profile image URL")

    # Auth source and verification
    provider: str = Field(..., description="github | google | email")
    provider_id: str = Field(..., description="Provider-specific ID or email sentinel ID")
    signup_method: str = Field(default=OAUTH_SIGNUP_METHOD, description="oauth | email_otp")
    email_verified_at: Optional[datetime] = Field(default=None)
    signup_ip: str = Field(default="", description="Signup request IP")
    signup_subnet: str = Field(default="", description="Signup request subnet")
    credit_policy: str = Field(
        default=OAUTH_TRIAL_CREDIT_POLICY,
        description="oauth_trial | email_no_trial | manual_review",
    )
    risk_flags: Dict[str, Any] = Field(default_factory=dict, description="Abuse/risk metadata")

    # Linked Rhumb resources
    organization_id: str = Field(default="", description="Default org ID")
    default_agent_id: str = Field(default="", description="Default agent ID")

    # Status
    status: str = Field(default="active", description="active | disabled")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── Store ────────────────────────────────────────────────────────────


class UserStore:
    """Manage unified users in Supabase (or in-memory for tests)."""

    def __init__(self, supabase_client: Any = None) -> None:
        self.supabase = supabase_client
        self._mem: Dict[str, Dict[str, Any]] = {}

    async def find_by_provider(
        self, provider: str, provider_id: str
    ) -> Optional[UserSchema]:
        """Look up a user by provider + provider ID."""
        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("users")
                    .select("*")
                    .eq("provider", provider)
                    .eq("provider_id", provider_id)
                    .single()
                    .execute()
                )
                if response.data:
                    return self._row_to_schema(response.data)
            except Exception:
                return None
        else:
            for row in self._mem.values():
                if row["provider"] == provider and row["provider_id"] == provider_id:
                    return self._row_to_schema(row)
        return None

    async def find_by_email(self, email: str) -> Optional[UserSchema]:
        """Look up user by email."""
        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("users")
                    .select("*")
                    .eq("email", email)
                    .single()
                    .execute()
                )
                if response.data:
                    return self._row_to_schema(response.data)
            except Exception:
                return None
        else:
            for row in self._mem.values():
                if row["email"] == email:
                    return self._row_to_schema(row)
        return None

    async def create_user(
        self,
        email: str,
        name: str,
        provider: str,
        provider_id: str,
        avatar_url: str = "",
        organization_id: str = "",
        default_agent_id: str = "",
        signup_method: str = OAUTH_SIGNUP_METHOD,
        email_verified_at: Optional[datetime] = None,
        signup_ip: str = "",
        signup_subnet: str = "",
        credit_policy: str = OAUTH_TRIAL_CREDIT_POLICY,
        risk_flags: Optional[Dict[str, Any]] = None,
    ) -> UserSchema:
        """Create a new user record."""
        user_id = str(uuid.uuid4())
        now = _utcnow()
        verified_at = email_verified_at or (
            now if signup_method == OAUTH_SIGNUP_METHOD else None
        )

        row: Dict[str, Any] = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "avatar_url": avatar_url,
            "provider": provider,
            "provider_id": provider_id,
            "signup_method": signup_method,
            "email_verified_at": verified_at.isoformat() if verified_at else None,
            "signup_ip": signup_ip,
            "signup_subnet": signup_subnet,
            "credit_policy": credit_policy,
            "risk_flags": risk_flags or {},
            "organization_id": organization_id,
            "default_agent_id": default_agent_id,
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self.supabase is not None:
            await self.supabase.table("users").insert(row).execute()
        else:
            self._mem[user_id] = row

        return self._row_to_schema(row)

    async def update_user(
        self, user_id: str, **kwargs: Any
    ) -> Optional[UserSchema]:
        """Update user fields."""
        kwargs["updated_at"] = _utcnow().isoformat()

        if self.supabase is not None:
            await (
                self.supabase.table("users")
                .update(kwargs)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            if user_id not in self._mem:
                return None
            self._mem[user_id].update(kwargs)

        return await self.get_user(user_id)

    async def get_user(self, user_id: str) -> Optional[UserSchema]:
        """Retrieve user by ID."""
        if self.supabase is not None:
            try:
                response = await (
                    self.supabase.table("users")
                    .select("*")
                    .eq("user_id", user_id)
                    .single()
                    .execute()
                )
                if response.data:
                    return self._row_to_schema(response.data)
            except Exception:
                return None
        else:
            row = self._mem.get(user_id)
            if row:
                return self._row_to_schema(row)
        return None

    @staticmethod
    def _row_to_schema(row: Dict[str, Any]) -> UserSchema:
        risk_flags = row.get("risk_flags", {})
        if not isinstance(risk_flags, dict):
            risk_flags = {}

        return UserSchema(
            user_id=row["user_id"],
            email=row["email"],
            name=row.get("name", ""),
            avatar_url=row.get("avatar_url", ""),
            provider=row["provider"],
            provider_id=row["provider_id"],
            signup_method=row.get("signup_method", OAUTH_SIGNUP_METHOD),
            email_verified_at=row.get("email_verified_at"),
            signup_ip=row.get("signup_ip", ""),
            signup_subnet=row.get("signup_subnet", ""),
            credit_policy=row.get("credit_policy", OAUTH_TRIAL_CREDIT_POLICY),
            risk_flags=risk_flags,
            organization_id=row.get("organization_id", ""),
            default_agent_id=row.get("default_agent_id", ""),
            status=row.get("status", "active"),
            created_at=row.get("created_at", _utcnow()),
            updated_at=row.get("updated_at", _utcnow()),
        )


# ── Singleton ────────────────────────────────────────────────────────

_user_store: Optional[UserStore] = None


def get_user_store(supabase_client: Any = None) -> UserStore:
    """Return (or create) the global UserStore singleton."""
    global _user_store
    if _user_store is None:
        _user_store = UserStore(supabase_client)
    return _user_store


def reset_user_store() -> None:
    """Reset the singleton (for tests)."""
    global _user_store
    _user_store = None


def is_email_signup(user: UserSchema) -> bool:
    """Return whether the user came through the email OTP signup path."""
    return user.signup_method == EMAIL_OTP_SIGNUP_METHOD


def has_verified_email(user: UserSchema) -> bool:
    """Return whether the user has a verified email on record."""
    return user.email_verified_at is not None
