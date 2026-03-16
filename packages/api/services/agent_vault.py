"""Agent Vault — Mode 3 credential execution.

Agents complete a ceremony to learn how to get their own API credentials,
then pass tokens per-request via X-Agent-Token header. Rhumb NEVER stores
the token — it's used for the single upstream request and then forgotten.

Security invariants:
- Token is NEVER persisted to any database or log
- Token is NEVER returned in any response
- Token format is validated before use (prefix, pattern)
- Optional live verification against the service's test endpoint
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote

import httpx

from routes._supabase import supabase_fetch

logger = logging.getLogger(__name__)


class AgentVaultTokenValidator:
    """Validates agent-provided tokens before use.

    Checks:
    1. Token is not empty
    2. Token matches expected format (prefix and/or regex pattern)
    3. Optional: live verification against service endpoint
    """

    async def get_ceremony(self, service_slug: str) -> dict | None:
        """Fetch ceremony skill for a service."""
        rows = await supabase_fetch(
            f"ceremony_skills?service_slug=eq.{quote(service_slug)}"
            f"&enabled=eq.true"
            f"&select=id,service_slug,display_name,description,auth_type,"
            f"steps,token_pattern,token_prefix,verify_endpoint,verify_method,"
            f"verify_expected_status,difficulty,estimated_minutes,requires_human,"
            f"documentation_url"
            f"&limit=1"
        )
        return rows[0] if rows else None

    async def list_ceremonies(self) -> list[dict]:
        """List all available ceremony skills."""
        rows = await supabase_fetch(
            "ceremony_skills?enabled=eq.true"
            "&select=service_slug,display_name,description,auth_type,"
            "difficulty,estimated_minutes,requires_human,documentation_url"
            "&order=difficulty.asc,service_slug.asc"
        )
        return rows or []

    def validate_format(
        self,
        token: str,
        token_prefix: str | None = None,
        token_pattern: str | None = None,
    ) -> tuple[bool, str | None]:
        """Validate token format without touching the network.

        Returns (is_valid, error_message).
        """
        if not token or not token.strip():
            return False, "Token is empty"

        token = token.strip()

        if token_prefix and not token.startswith(token_prefix):
            return False, f"Token should start with '{token_prefix}'"

        if token_pattern:
            try:
                if not re.fullmatch(token_pattern, token):
                    return False, "Token format does not match expected pattern"
            except re.error:
                # Bad regex in DB — skip pattern check
                logger.warning(f"Invalid token_pattern regex: {token_pattern}")

        return True, None

    async def verify_live(
        self,
        token: str,
        service_slug: str,
        ceremony: dict,
    ) -> tuple[bool, str | None]:
        """Optional live verification — test the token against the service.

        Returns (is_valid, error_message).
        SECURITY: token is used only in this transient request, never stored.
        """
        verify_endpoint = ceremony.get("verify_endpoint")
        if not verify_endpoint:
            return True, None  # No verification endpoint — skip

        # Resolve service domain
        svc_rows = await supabase_fetch(
            f"services?slug=eq.{quote(service_slug)}&select=api_domain&limit=1"
        )
        if not svc_rows or not svc_rows[0].get("api_domain"):
            return True, None  # Can't verify without domain — pass

        domain = svc_rows[0]["api_domain"]
        base_url = domain if domain.startswith("http") else f"https://{domain}"

        method = ceremony.get("verify_method", "GET")
        expected_status = ceremony.get("verify_expected_status", 200)

        auth_type = ceremony.get("auth_type", "api_key")
        headers: dict[str, str] = {}

        if auth_type == "basic_auth":
            import base64
            encoded = base64.b64encode(token.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif service_slug == "anthropic":
            headers["x-api-key"] = token
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.request(
                    method=method,
                    url=f"{base_url}{verify_endpoint}",
                    headers=headers,
                )

            if resp.status_code == expected_status:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Token is invalid or expired"
            else:
                # Non-auth error — token might be fine
                return True, None

        except httpx.HTTPError as e:
            # Network error — don't block on verification failure
            logger.warning(f"Live verification failed for {service_slug}: {e}")
            return True, None


# Singleton
_validator: AgentVaultTokenValidator | None = None


def get_vault_validator() -> AgentVaultTokenValidator:
    global _validator
    if _validator is None:
        _validator = AgentVaultTokenValidator()
    return _validator
