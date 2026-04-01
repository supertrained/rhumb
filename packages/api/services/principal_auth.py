"""AUD-5: Authenticated principal verification for kill switch operations.

Replaces caller-supplied principal strings with verified identities.

Design:
- Principals are registered admin identities (not just strings)
- Each principal has a unique ID and must authenticate via admin key + principal_id
- The kill switch registry now requires VerifiedPrincipal objects, not strings
- Two-person auth is enforced on verified identity, not self-reported name
- Principal registry can be backed by DB or config (starts with config)

Production principal registration:
- Set RHUMB_ADMIN_PRINCIPALS as JSON: [{"id": "pedro", "name": "Pedro", "role": "operator"}, ...]
- Or store in 1Password / Supabase for dynamic management
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VerifiedPrincipal:
    """A verified admin principal identity.

    This is NOT a caller-supplied string. It is derived from:
    1. A valid admin key authentication
    2. A registered principal_id that exists in the principal registry
    3. Timestamp of verification (for freshness checks)
    """
    principal_id: str
    name: str
    role: str  # "operator", "admin", "security"
    verified_at: float  # monotonic timestamp
    verification_method: str  # "admin_key", "oauth", "hardware_key"

    def is_fresh(self, max_age_seconds: float = 300.0) -> bool:
        """Check if this verification is still fresh (default 5 min)."""
        return (time.monotonic() - self.verified_at) < max_age_seconds


@dataclass(frozen=True, slots=True)
class PrincipalRegistration:
    """A registered admin principal."""
    principal_id: str
    name: str
    role: str
    # In production, this would be a hashed secret or linked to an auth provider
    secret_hash: str = ""  # SHA-256 of principal-specific secret


class PrincipalRegistry:
    """Registry of authorized admin principals.

    Loads from environment or configuration. In production, this should
    be backed by a durable store with proper access controls.
    """

    def __init__(self, principals: list[PrincipalRegistration] | None = None) -> None:
        self._principals: dict[str, PrincipalRegistration] = {}
        if principals:
            for p in principals:
                self._principals[p.principal_id] = p
        else:
            self._load_from_env()

    def _load_from_env(self) -> None:
        """Load principals from RHUMB_ADMIN_PRINCIPALS env var."""
        raw = os.environ.get("RHUMB_ADMIN_PRINCIPALS", "")
        if not raw:
            # Default: single operator principal for bootstrap
            self._principals["operator"] = PrincipalRegistration(
                principal_id="operator",
                name="Default Operator",
                role="operator",
            )
            logger.info("principal_registry: using default operator principal")
            return

        try:
            entries = json.loads(raw)
            for entry in entries:
                pid = entry["id"]
                self._principals[pid] = PrincipalRegistration(
                    principal_id=pid,
                    name=entry.get("name", pid),
                    role=entry.get("role", "operator"),
                    secret_hash=entry.get("secret_hash", ""),
                )
            logger.info("principal_registry: loaded %d principals", len(self._principals))
        except Exception:
            logger.warning("principal_registry: failed to parse RHUMB_ADMIN_PRINCIPALS", exc_info=True)

    def verify(
        self,
        principal_id: str,
        *,
        principal_secret: str | None = None,
    ) -> VerifiedPrincipal | None:
        """Verify a principal identity.

        Returns a VerifiedPrincipal if the principal_id exists in the registry
        and (if configured) the principal_secret matches. Returns None if
        verification fails.
        """
        registration = self._principals.get(principal_id)
        if registration is None:
            logger.warning("principal_verify_failed: unknown principal_id=%s", principal_id)
            return None

        # If a secret_hash is configured, verify the secret
        if registration.secret_hash:
            if not principal_secret:
                logger.warning("principal_verify_failed: secret required for %s", principal_id)
                return None
            provided_hash = hashlib.sha256(principal_secret.encode()).hexdigest()
            if not hmac.compare_digest(provided_hash, registration.secret_hash):
                logger.warning("principal_verify_failed: bad secret for %s", principal_id)
                return None

        return VerifiedPrincipal(
            principal_id=registration.principal_id,
            name=registration.name,
            role=registration.role,
            verified_at=time.monotonic(),
            verification_method="admin_key",
        )

    def get(self, principal_id: str) -> PrincipalRegistration | None:
        """Look up a registered principal."""
        return self._principals.get(principal_id)

    @property
    def count(self) -> int:
        return len(self._principals)

    def list_ids(self) -> list[str]:
        return list(self._principals.keys())


# Module singleton
_registry: PrincipalRegistry | None = None


def get_principal_registry() -> PrincipalRegistry:
    global _registry
    if _registry is None:
        _registry = PrincipalRegistry()
    return _registry
