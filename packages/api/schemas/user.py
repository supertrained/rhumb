"""User identity schema for OAuth-authenticated humans.

Agents have identities in ``agent_identity.py``.  This schema covers
human users who sign up via OAuth (GitHub / Google) and manage agents
through the dashboard.

A user owns one default organization and one default agent — created
automatically on first login.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# ── Schema ───────────────────────────────────────────────────────────


class UserSchema(BaseModel):
    """Human user record (mirrors ``users`` table in Supabase)."""

    user_id: str = Field(..., description="UUID user identifier")
    email: str = Field(..., description="Email from OAuth provider")
    name: str = Field(default="", description="Display name")
    avatar_url: str = Field(default="", description="Profile image URL")

    # OAuth provider info
    provider: str = Field(..., description="github | google")
    provider_id: str = Field(..., description="Provider-specific user ID")

    # Linked Rhumb resources
    organization_id: str = Field(default="", description="Default org ID")
    default_agent_id: str = Field(default="", description="Default agent ID")

    # Status
    status: str = Field(default="active", description="active | disabled")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── Store ────────────────────────────────────────────────────────────


class UserStore:
    """Manage human users in Supabase (or in-memory for tests)."""

    def __init__(self, supabase_client: Any = None) -> None:
        self.supabase = supabase_client
        self._mem: Dict[str, Dict[str, Any]] = {}

    async def find_by_provider(
        self, provider: str, provider_id: str
    ) -> Optional[UserSchema]:
        """Look up user by OAuth provider + provider ID."""
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
    ) -> UserSchema:
        """Create a new user record."""
        user_id = str(uuid.uuid4())
        now = _utcnow()

        row: Dict[str, Any] = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "avatar_url": avatar_url,
            "provider": provider,
            "provider_id": provider_id,
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
        return UserSchema(
            user_id=row["user_id"],
            email=row["email"],
            name=row.get("name", ""),
            avatar_url=row.get("avatar_url", ""),
            provider=row["provider"],
            provider_id=row["provider_id"],
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
