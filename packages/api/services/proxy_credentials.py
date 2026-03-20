"""Credential store for proxy service.

Loads and caches provider credentials with TTL-based refresh.
In production, credentials are loaded from 1Password via ``sop`` CLI,
with environment variable fallback for containerized deployments.
In tests, the ``_load_service`` method is mocked via fixtures.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class CredentialEntry:
    """Single credential (API key, token, etc.)."""

    credential_type: str  # "api_key", "oauth_token", "basic_auth"
    value: str
    expires_at: Optional[datetime] = None
    loaded_at: datetime = field(default_factory=datetime.utcnow)

    def is_expired(self) -> bool:
        """Check whether the credential has passed its expiration time."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


@dataclass
class ProviderCredentials:
    """All credentials for a single provider."""

    service: str  # "stripe", "slack", etc.
    credentials: Dict[str, CredentialEntry] = field(default_factory=dict)
    last_refreshed: datetime = field(default_factory=datetime.utcnow)
    ttl_minutes: int = 60  # refresh every 60 min

    def is_stale(self) -> bool:
        """Return ``True`` when the TTL window has elapsed."""
        elapsed = (datetime.utcnow() - self.last_refreshed).total_seconds() / 60
        return elapsed > self.ttl_minutes


# Mapping of 1Password item names to (service, credential_key) pairs.
_1PASSWORD_MAP: Dict[str, tuple[str, str]] = {
    "stripe_api_key": ("stripe", "api_key"),
    "slack_app_token": ("slack", "oauth_token"),
    "github_token": ("github", "api_token"),
    "twilio_credentials": ("twilio", "basic_auth"),
    "sendgrid_api_key": ("sendgrid", "api_key"),
    "firecrawl_api_key": ("firecrawl", "api_key"),
    "apify_api_token": ("apify", "api_token"),
    "apollo_api_key": ("apollo", "api_key"),
    "pdl_api_key": ("pdl", "api_key"),
}

# Environment variable fallback: RHUMB_CREDENTIAL_<SERVICE>_<KEY>=<value>
# Example: RHUMB_CREDENTIAL_SLACK_OAUTH_TOKEN=xoxb-...
_ENV_FALLBACK: Dict[str, tuple[str, str]] = {
    "slack": ("RHUMB_CREDENTIAL_SLACK_OAUTH_TOKEN", "oauth_token"),
    "stripe": ("RHUMB_CREDENTIAL_STRIPE_API_KEY", "api_key"),
    "github": ("RHUMB_CREDENTIAL_GITHUB_API_TOKEN", "api_token"),
    "twilio": ("RHUMB_CREDENTIAL_TWILIO_BASIC_AUTH", "basic_auth"),
    "sendgrid": ("RHUMB_CREDENTIAL_SENDGRID_API_KEY", "api_key"),
    "firecrawl": ("RHUMB_CREDENTIAL_FIRECRAWL_API_KEY", "api_key"),
    "apify": ("RHUMB_CREDENTIAL_APIFY_API_TOKEN", "api_token"),
    "apollo": ("RHUMB_CREDENTIAL_APOLLO_API_KEY", "api_key"),
    "pdl": ("RHUMB_CREDENTIAL_PDL_API_KEY", "api_key"),
}


class CredentialStore:
    """Manage provider credentials with 1Password integration and in-memory cache."""

    SUPPORTED_SERVICES: List[str] = ["stripe", "slack", "github", "twilio", "sendgrid", "firecrawl", "apify", "apollo", "pdl"]

    def __init__(self, *, auto_load: bool = True) -> None:
        self._cache: Dict[str, ProviderCredentials] = {}
        self._refresh_in_progress: Dict[str, bool] = {}
        self._audit_entries: List[Dict[str, Any]] = []
        if auto_load:
            self._initial_load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _initial_load(self) -> None:
        """Load all provider credentials from 1Password vault at startup."""
        for service in self.SUPPORTED_SERVICES:
            self._load_service(service)

    def _load_service(self, service: str) -> None:
        """Load credentials for *service* from 1Password.

        Override / mock in tests.  In production calls ``sop`` CLI.
        """
        item_name = self._item_name_for(service)
        if item_name is None:
            return

        try:
            result = subprocess.run(
                [
                    "sop",
                    "item",
                    "get",
                    item_name,
                    "--vault",
                    "OpenClaw Agents",
                    "--fields",
                    "credential",
                    "--reveal",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    _, cred_key = _1PASSWORD_MAP.get(item_name, (service, "default"))
                    entry = CredentialEntry(
                        credential_type=cred_key,
                        value=value,
                        loaded_at=datetime.utcnow(),
                    )
                    self._cache[service] = ProviderCredentials(
                        service=service,
                        credentials={cred_key: entry},
                        last_refreshed=datetime.utcnow(),
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # If sop didn't load the credential, try environment variable fallback.
        if service not in self._cache or not self._cache[service].credentials:
            self._load_from_env(service)

    def _load_from_env(self, service: str) -> None:
        """Fallback: load credentials from environment variables."""
        fallback = _ENV_FALLBACK.get(service)
        if fallback is None:
            return

        env_var, cred_key = fallback
        value = os.environ.get(env_var, "").strip()
        if not value:
            return

        entry = CredentialEntry(
            credential_type=cred_key,
            value=value,
            loaded_at=datetime.utcnow(),
        )
        self._cache[service] = ProviderCredentials(
            service=service,
            credentials={cred_key: entry},
            last_refreshed=datetime.utcnow(),
        )

    @staticmethod
    def _item_name_for(service: str) -> Optional[str]:
        """Map service name to 1Password item name."""
        for item, (svc, _) in _1PASSWORD_MAP.items():
            if svc == service:
                return item
        return None

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get_credential(self, service: str, key: str = "default") -> Optional[str]:
        """Retrieve a credential value.

        Checks the in-memory cache first, then falls back to the generic
        environment variable pattern ``RHUMB_CREDENTIAL_{SERVICE}_{KEY}``
        for dynamic (non-hardcoded) services.

        Args:
            service: Provider name (``"stripe"``, ``"resend"`` …).
            key: Credential key within service (e.g. ``"api_key"``).

        Returns:
            Credential value if found and not expired, else ``None``.
        """
        provider = self._cache.get(service)
        if provider is not None:
            entry = provider.credentials.get(key)
            if entry is not None and not entry.is_expired():
                return entry.value

        # Dynamic env-var fallback for any service:
        # RHUMB_CREDENTIAL_RESEND_API_KEY, RHUMB_CREDENTIAL_OPENAI_API_KEY, etc.
        env_var = f"RHUMB_CREDENTIAL_{service.upper().replace('-', '_')}_{key.upper()}"
        value = os.environ.get(env_var, "").strip()
        if value:
            # Cache it so we don't re-read env every call
            self.set_credential(service, key, value)
            return value

        return None

    def callable_services(self) -> list[str]:
        """Return service names that have at least one valid, non-expired credential.

        A service is ``callable`` when the proxy can actually inject auth on
        its behalf — i.e., a real credential exists in the cache (loaded from
        1Password or an environment variable fallback).  Services that are
        registered in ``SERVICE_REGISTRY`` but have no credential are *not*
        included here.
        """
        result = []
        for service in self.SUPPORTED_SERVICES:
            provider = self._cache.get(service)
            if provider and any(
                not entry.is_expired() for entry in provider.credentials.values()
            ):
                result.append(service)
        return result

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    async def refresh_if_stale(self, service: str) -> None:
        """Refresh a service's credentials when the TTL has elapsed."""
        provider = self._cache.get(service)
        if provider is not None and not provider.is_stale():
            return

        if self._refresh_in_progress.get(service, False):
            return  # another refresh already running

        self._refresh_in_progress[service] = True
        try:
            self._load_service(service)
        finally:
            self._refresh_in_progress[service] = False

    # ------------------------------------------------------------------
    # Manual cache management (used by tests & admin)
    # ------------------------------------------------------------------

    def set_credential(
        self,
        service: str,
        key: str,
        value: str,
        *,
        expires_at: Optional[datetime] = None,
        ttl_minutes: int = 60,
    ) -> None:
        """Manually inject a credential into the cache (useful for tests)."""
        entry = CredentialEntry(
            credential_type=key,
            value=value,
            expires_at=expires_at,
            loaded_at=datetime.utcnow(),
        )
        if service not in self._cache:
            self._cache[service] = ProviderCredentials(
                service=service,
                ttl_minutes=ttl_minutes,
            )
        self._cache[service].credentials[key] = entry
        self._cache[service].last_refreshed = datetime.utcnow()

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def audit_log(self, service: str, agent_id: str, action: str = "used") -> None:
        """Record credential usage for the audit trail."""
        self._audit_entries.append(
            {
                "service": service,
                "agent_id": agent_id,
                "action": action,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    @property
    def audit_entries(self) -> List[Dict[str, Any]]:
        """Expose the in-memory audit log (for testing & inspection)."""
        return list(self._audit_entries)


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_credential_store: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    """Return (or create) the global :class:`CredentialStore` singleton."""
    global _credential_store
    if _credential_store is None:
        _credential_store = CredentialStore()
    return _credential_store
