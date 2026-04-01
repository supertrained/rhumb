"""AUD-5: Authenticated principal verification for kill switches.

Problem: The two-person kill switch accepts caller-provided string identities.
An attacker with admin access can fabricate two different principal strings
to approve their own global kill request.

Solution: Principals must be verified authenticated identities extracted from
the request context — never from the request body.

Design:
- PrincipalIdentity is a frozen dataclass representing a verified principal
- extract_principal() extracts identity from the authenticated admin session
- The kill switch registry accepts PrincipalIdentity objects, not raw strings
- Identity comparison uses unique identifiers (user_id, agent_id), not display names
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PrincipalType(str, Enum):
    """Type of authenticated principal."""

    ADMIN_USER = "admin_user"      # Human admin via OAuth/email session
    ADMIN_AGENT = "admin_agent"    # Agent with admin privileges
    SERVICE_KEY = "service_key"    # Service-level admin API key


@dataclass(frozen=True, slots=True)
class PrincipalIdentity:
    """A verified, authenticated principal identity.

    Must be extracted from the request's authentication context,
    never from the request body.
    """

    principal_type: PrincipalType
    # Unique identifier that cannot be forged:
    # - For admin users: user ID from the auth session (e.g., "usr_abc123")
    # - For admin agents: agent ID from the API key lookup (e.g., "agt_xyz789")
    # - For service keys: SHA-256 hash of the key prefix (e.g., "skey_a1b2c3")
    unique_id: str
    # Human-readable label for audit logs (NOT used for identity comparison)
    display_name: str
    # When the identity was verified
    verified_at: datetime

    @property
    def canonical_id(self) -> str:
        """The canonical identity string used for same-person comparison.

        This is what determines whether two principals are the same person.
        Uses unique_id, NOT display_name.
        """
        return f"{self.principal_type.value}:{self.unique_id}"

    def is_same_principal(self, other: PrincipalIdentity) -> bool:
        """Check if two principals are the same authenticated entity.

        Uses canonical_id for comparison, not display names.
        Two different display names with the same underlying identity
        are correctly identified as the same person.
        """
        return self.canonical_id == other.canonical_id


def extract_principal_from_admin_key(admin_key: str) -> PrincipalIdentity:
    """Extract a verified principal from an admin API key.

    The key itself is the proof of identity. We hash a prefix
    to create a stable, non-secret identifier.
    """
    # Use first 16 chars of SHA-256 of the full key as stable ID
    key_hash = hashlib.sha256(admin_key.encode()).hexdigest()[:16]
    return PrincipalIdentity(
        principal_type=PrincipalType.SERVICE_KEY,
        unique_id=f"skey_{key_hash}",
        display_name=f"admin_key_{key_hash[:8]}",
        verified_at=datetime.now(timezone.utc),
    )


def extract_principal_from_session(
    user_id: str,
    email: str | None = None,
    name: str | None = None,
) -> PrincipalIdentity:
    """Extract a verified principal from an authenticated user session."""
    return PrincipalIdentity(
        principal_type=PrincipalType.ADMIN_USER,
        unique_id=user_id,
        display_name=email or name or user_id,
        verified_at=datetime.now(timezone.utc),
    )


def extract_principal_from_agent(
    agent_id: str,
    label: str | None = None,
) -> PrincipalIdentity:
    """Extract a verified principal from an authenticated agent."""
    return PrincipalIdentity(
        principal_type=PrincipalType.ADMIN_AGENT,
        unique_id=agent_id,
        display_name=label or agent_id,
        verified_at=datetime.now(timezone.utc),
    )


@dataclass(frozen=True, slots=True)
class PendingApproval:
    """A pending two-person approval with verified requester identity."""

    request_id: str
    requester: PrincipalIdentity
    reason: str
    requested_at: datetime
    expires_at: float  # monotonic time
    # Additional context for audit
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def can_approve(self, approver: PrincipalIdentity) -> tuple[bool, str]:
        """Check if this approver can approve this request.

        Returns (allowed, reason).
        """
        if self.requester.is_same_principal(approver):
            return False, (
                f"Same principal cannot request and approve: "
                f"{self.requester.canonical_id} == {approver.canonical_id}"
            )
        return True, "approved"
