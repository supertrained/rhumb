"""Rhumb-managed executor — Mode 2 credential execution.

When a capability has Rhumb's own credentials configured, agents can
execute it with zero setup. The agent sends the *what* (capability + params),
and Rhumb handles the *how* (credential injection, request construction,
upstream call).

Security invariants:
- Rhumb's credentials are NEVER returned in responses
- Credential env var names are stored in the DB but values come from os.environ
- Underlying service identity is visible (not hidden) — transparency over obscurity
"""

from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from routes._supabase import supabase_fetch, supabase_insert, supabase_patch
from services.service_slugs import normalize_proxy_slug

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_managed_executor: Optional["RhumbManagedExecutor"] = None


def get_managed_executor() -> "RhumbManagedExecutor":
    """Get or create the singleton RhumbManagedExecutor."""
    global _managed_executor
    if _managed_executor is None:
        _managed_executor = RhumbManagedExecutor()
    return _managed_executor


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

class RhumbManagedExecutor:
    """Executes capabilities using Rhumb's own credentials.

    The executor:
    1. Looks up the managed capability config from the DB
    2. Resolves the service's API domain
    3. Loads Rhumb's credentials from environment variables
    4. Constructs and sends the request
    5. Returns the response with execution metadata

    Agent-provided body fields are merged with any default template.
    """

    async def is_managed(self, capability_id: str, service_slug: str | None = None) -> bool:
        """Check if a capability has a managed execution path."""
        path = (
            f"rhumb_managed_capabilities?capability_id=eq.{quote(capability_id)}"
            f"&enabled=eq.true&select=id&limit=1"
        )
        if service_slug:
            path += f"&service_slug=eq.{quote(normalize_proxy_slug(service_slug))}"
        rows = await supabase_fetch(path)
        return bool(rows)

    async def get_managed_config(
        self, capability_id: str, service_slug: str | None = None
    ) -> dict | None:
        """Fetch the managed capability config."""
        path = (
            f"rhumb_managed_capabilities?capability_id=eq.{quote(capability_id)}"
            f"&enabled=eq.true"
            f"&select=id,capability_id,service_slug,description,"
            f"credential_env_keys,default_method,default_path,default_headers,"
            f"daily_limit_per_agent"
        )
        if service_slug:
            path += f"&service_slug=eq.{quote(normalize_proxy_slug(service_slug))}"
        path += "&limit=1"
        rows = await supabase_fetch(path)
        return rows[0] if rows else None

    async def list_managed(self) -> list[dict]:
        """List all enabled managed capabilities (public catalog)."""
        rows = await supabase_fetch(
            "rhumb_managed_capabilities?enabled=eq.true"
            "&select=capability_id,service_slug,description,daily_limit_per_agent"
            "&order=capability_id.asc"
        )
        return rows or []

    async def execute(
        self,
        capability_id: str,
        agent_id: str,
        body: dict | None = None,
        params: dict | None = None,
        service_slug: str | None = None,
        interface: str = "rest",
        execution_id: str | None = None,
    ) -> dict:
        """Execute a managed capability using Rhumb's credentials.

        Args:
            capability_id: e.g. "email.send"
            agent_id: calling agent's identity
            body: request body (merged with defaults)
            params: query parameters
            service_slug: explicit provider (or auto-select)
            interface: client interface type
            execution_id: optional pre-created execution row to update in-place

        Returns:
            Execution result dict with upstream response + metadata.

        Raises:
            HTTPException on failures.
        """
        config = await self.get_managed_config(capability_id, service_slug)
        if config is None:
            raise HTTPException(
                status_code=503,
                detail=f"No managed execution path for '{capability_id}'"
                + (f" via '{service_slug}'" if service_slug else ""),
            )

        slug = config["service_slug"]
        method = config["default_method"]
        path = config["default_path"]
        default_headers = config.get("default_headers") or {}

        # Path template interpolation: replace {param} with values from body or params
        if "{" in path:
            sources = {**(params or {}), **(body or {})}
            for key, val in sources.items():
                path = path.replace(f"{{{key}}}", str(val))
            # If any unresolved templates remain, strip them (e.g. /{ip} → /)
            import re as _re
            path = _re.sub(r"\{[^}]+\}", "", path)

        # Resolve API domain
        api_domain = await self._get_api_domain(slug)
        if not api_domain:
            raise HTTPException(
                status_code=500,
                detail=f"No API domain configured for managed service '{slug}'",
            )

        base_url = api_domain if api_domain.startswith("http") else f"https://{api_domain}"

        # Load Rhumb's credentials from env and inject into headers/params/body
        credential_keys = config.get("credential_env_keys", [])
        headers = dict(default_headers)
        headers, params, body = self._inject_credentials(
            slug, credential_keys, headers, params, body
        )

        # For GET/HEAD/DELETE: promote remaining body fields to query params,
        # then null the body.  (Body values may already have been consumed by path
        # template substitution above; any that remain need to reach the upstream as
        # query-string parameters — e.g. Brave Search requires `q` as a query param.)
        if method.upper() in ("GET", "HEAD", "DELETE"):
            if body:
                if params is None:
                    params = {}
                for k, v in body.items():
                    # Don't overwrite credential params already injected
                    if k not in params:
                        params[k] = v
            final_body = None
        else:
            final_body = body

        # Execute
        prelogged_execution = execution_id is not None
        execution_id = execution_id or f"exec_{uuid.uuid4().hex}"
        request_start = time.perf_counter()
        upstream_status: int | None = None
        upstream_response: Any = None
        upstream_latency_ms = 0.0
        success = False
        error_message: str | None = None

        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
                upstream_start = time.perf_counter()
                resp = await client.request(
                    method=method,
                    url=path if path.startswith("/") else f"/{path}",
                    headers=headers,
                    json=final_body,
                    params=params,
                )
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000

            upstream_status = resp.status_code
            try:
                upstream_response = resp.json()
            except Exception:
                upstream_response = resp.text

            success = upstream_status < 500

        except httpx.HTTPError as e:
            error_message = str(e)
            raise HTTPException(
                status_code=502,
                detail=f"Managed execution failed: {error_message}",
            )

        total_latency_ms = (time.perf_counter() - request_start) * 1000

        # Log execution
        update_payload = {
            "provider_used": slug,
            "credential_mode": "rhumb_managed",
            "method": method,
            "path": path,
            "upstream_status": upstream_status,
            "success": success,
            "total_latency_ms": round(total_latency_ms, 1),
            "upstream_latency_ms": round(upstream_latency_ms, 1),
            "fallback_attempted": False,
            "fallback_provider": None,
            "idempotency_key": None,
            "error_message": error_message,
            "interface": interface,
        }
        if not prelogged_execution:
            update_payload["cost_estimate_usd"] = None  # managed — Rhumb absorbs cost
        updated = await supabase_patch(
            f"capability_executions?id=eq.{quote(execution_id)}",
            update_payload,
        )
        if not updated:
            await supabase_insert("capability_executions", {
                "id": execution_id,
                "agent_id": agent_id,
                "capability_id": capability_id,
                **update_payload,
            })

        return {
            "capability_id": capability_id,
            "provider_used": slug,
            "credential_mode": "rhumb_managed",
            "upstream_status": upstream_status,
            "upstream_response": upstream_response,
            "latency_ms": round(total_latency_ms, 1),
            "execution_id": execution_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_api_domain(self, service_slug: str) -> str | None:
        """Resolve service API domain."""
        rows = await supabase_fetch(
            f"services?slug=eq.{quote(service_slug)}&select=api_domain&limit=1"
        )
        if rows and rows[0].get("api_domain"):
            return rows[0]["api_domain"]
        return None

    # Per-service auth injection strategies.
    # Key = service_slug, value = (header_name, prefix|None).
    # If prefix is None, the raw value is set as the header value.
    # Special value "query:key_name" means inject as query parameter.
    _AUTH_STRATEGIES: dict[str, tuple[str, str | None]] = {
        # Custom header auth
        "algolia": ("X-Algolia-API-Key", None),
        "postmark": ("X-Postmark-Server-Token", None),
        "elevenlabs": ("xi-api-key", None),
        "unstructured": ("unstructured-api-key", None),
        "brave-search": ("X-Subscription-Token", None),
        "apollo": ("X-Api-Key", None),
        "people-data-labs": ("X-API-Key", None),
        "google-ai": ("x-goog-api-key", None),
        # Token auth (non-Bearer Authorization header)
        "deepgram": ("Authorization", "Token "),
        # Query parameter auth (handled specially in execute)
        "google-maps": ("query:key", None),
        "google-places": ("query:key", None),
        "scraperapi": ("query:api_key", None),
        "ipinfo": ("query:token", None),
        # Body-injected auth
        "tavily": ("body:api_key", None),
    }

    def _inject_credentials(
        self,
        service_slug: str,
        credential_env_keys: list[str],
        headers: dict[str, str],
        params: dict | None = None,
        body: dict | None = None,
    ) -> tuple[dict[str, str], dict | None, dict | None]:
        """Inject Rhumb's credentials from environment variables.

        Returns (headers, params, body) — all potentially modified.

        Security: credential VALUES never leave this method —
        they go into headers/params/body sent upstream, but never returned
        in any response payload.
        """
        headers = headers.copy()
        params = dict(params) if params else {}
        body = dict(body) if body else body

        for env_key in credential_env_keys:
            value = os.environ.get(env_key)
            if value is None:
                raise HTTPException(
                    status_code=503,
                    detail=f"Managed credential not configured (missing env var)",
                )

            # Check for service-specific auth strategy
            strategy = self._AUTH_STRATEGIES.get(service_slug)
            if strategy:
                header_name, prefix = strategy
                if header_name.startswith("query:"):
                    # Inject as query parameter
                    param_name = header_name.split(":", 1)[1]
                    params[param_name] = value
                elif header_name.startswith("body:"):
                    # Inject into request body
                    body_key = header_name.split(":", 1)[1]
                    if body is None:
                        body = {}
                    body[body_key] = value
                else:
                    # Inject as custom header
                    headers[header_name] = f"{prefix}{value}" if prefix else value
            else:
                # Determine from env key naming convention
                key_lower = env_key.lower()
                if "basic" in key_lower:
                    encoded = base64.b64encode(value.encode()).decode()
                    headers["Authorization"] = f"Basic {encoded}"
                else:
                    # Default: Bearer token
                    headers["Authorization"] = f"Bearer {value}"

        return headers, params, body
