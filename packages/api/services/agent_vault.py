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
from services.service_slugs import CANONICAL_TO_PROXY, public_service_slug, public_service_slug_candidates

logger = logging.getLogger(__name__)


def _postgrest_in(values: list[str]) -> str:
    return ",".join(quote(value, safe="-_") for value in values)


def _canonicalize_known_service_aliases(
    text: object,
    *,
    preserve_canonical: str | None = None,
) -> str | None:
    if text is None:
        return None

    preserved = str(preserve_canonical or "").strip().lower() or None
    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
        if preserved and canonical.lower() == preserved:
            continue
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return str(text)

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], str(text))


def _canonicalize_ceremony_text(
    text: object,
    response_service_slug: str | None,
    stored_service_slug: str | None,
) -> str | None:
    if text is None:
        return None

    canonical = public_service_slug(response_service_slug)
    if canonical is None:
        return str(text)

    raw_stored_slug = str(stored_service_slug).strip().lower() if stored_service_slug else None
    preserve_human_shorthand = raw_stored_slug == canonical.lower()

    canonicalized = str(text)
    for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
        cleaned = str(candidate or "").strip()
        if not cleaned or cleaned.lower() == canonical.lower():
            continue

        pattern = re.compile(
            rf"(?<![a-z0-9-]){re.escape(cleaned)}(?![a-z0-9-])",
            re.IGNORECASE,
        )

        def _replace(match: re.Match[str]) -> str:
            matched = match.group(0)
            if preserve_human_shorthand and cleaned.isalpha() and matched == cleaned.upper():
                return matched
            return canonical

        canonicalized = pattern.sub(_replace, canonicalized)

    return _canonicalize_known_service_aliases(
        canonicalized,
        preserve_canonical=canonical if preserve_human_shorthand else None,
    )


class AgentVaultTokenValidator:
    """Validates agent-provided tokens before use.

    Checks:
    1. Token is not empty
    2. Token matches expected format (prefix and/or regex pattern)
    3. Optional: live verification against service endpoint
    """

    async def get_ceremony(self, service_slug: str) -> dict | None:
        """Fetch ceremony skill for a service."""
        slug_candidates = public_service_slug_candidates(service_slug)
        rows = await supabase_fetch(
            "ceremony_skills"
            f"?service_slug=in.({_postgrest_in(slug_candidates)})"
            f"&enabled=eq.true"
            f"&select=id,service_slug,display_name,description,auth_type,"
            f"steps,token_pattern,token_prefix,verify_endpoint,verify_method,"
            f"verify_expected_status,difficulty,estimated_minutes,requires_human,"
            f"documentation_url"
        )
        if not rows:
            return None

        for candidate in slug_candidates:
            for row in rows:
                if str(row.get("service_slug") or "").strip() == candidate:
                    canonical_slug = public_service_slug(row.get("service_slug")) or candidate
                    return {
                        **row,
                        "service_slug": canonical_slug,
                        "display_name": _canonicalize_ceremony_text(
                            row.get("display_name"), canonical_slug, row.get("service_slug")
                        ),
                        "description": _canonicalize_ceremony_text(
                            row.get("description"), canonical_slug, row.get("service_slug")
                        ),
                    }

        row = rows[0]
        canonical_slug = public_service_slug(row.get("service_slug")) or service_slug
        return {
            **row,
            "service_slug": canonical_slug,
            "display_name": _canonicalize_ceremony_text(
                row.get("display_name"), canonical_slug, row.get("service_slug")
            ),
            "description": _canonicalize_ceremony_text(
                row.get("description"), canonical_slug, row.get("service_slug")
            ),
        }

    async def list_ceremonies(self) -> list[dict]:
        """List all available ceremony skills."""
        rows = await supabase_fetch(
            "ceremony_skills?enabled=eq.true"
            "&select=service_slug,display_name,description,auth_type,"
            "difficulty,estimated_minutes,requires_human,documentation_url"
            "&order=difficulty.asc,service_slug.asc"
        ) or []

        canonical_rows: dict[str, dict] = {}
        for row in rows:
            canonical_slug = public_service_slug(row.get("service_slug"))
            if not canonical_slug:
                continue
            normalized_row = {
                **row,
                "service_slug": canonical_slug,
                "display_name": _canonicalize_ceremony_text(
                    row.get("display_name"), canonical_slug, row.get("service_slug")
                ),
                "description": _canonicalize_ceremony_text(
                    row.get("description"), canonical_slug, row.get("service_slug")
                ),
            }
            existing = canonical_rows.get(canonical_slug)
            if existing is None:
                canonical_rows[canonical_slug] = normalized_row
                continue
            existing_raw_slug = str(existing.get("service_slug") or "").strip()
            row_raw_slug = str(row.get("service_slug") or "").strip()
            if existing_raw_slug != canonical_slug and row_raw_slug == canonical_slug:
                canonical_rows[canonical_slug] = normalized_row

        return list(canonical_rows.values())

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
        service_candidates = public_service_slug_candidates(service_slug)
        svc_rows = await supabase_fetch(
            f"services?slug=in.({_postgrest_in(service_candidates)})&select=slug,api_domain"
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
