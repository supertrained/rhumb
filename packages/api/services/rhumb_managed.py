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
import json
import logging
import os
import time
import uuid
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from routes._supabase import supabase_fetch, supabase_insert, supabase_patch
from services.service_slugs import canonicalize_service_slug, normalize_proxy_slug

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

    @staticmethod
    def _service_slug_candidates(service_slug: str) -> list[str]:
        """Return alias candidates for managed-config lookups.

        Managed capability rows may be stored with canonical/public slugs
        (for example ``people-data-labs``) while some runtime callers still
        pass proxy-layer aliases (for example ``pdl``). Try both forms so
        managed execution works across canonical/proxy surfaces.
        """
        candidates: list[str] = []
        for candidate in (
            service_slug,
            canonicalize_service_slug(service_slug),
            normalize_proxy_slug(service_slug),
        ):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    async def is_managed(self, capability_id: str, service_slug: str | None = None) -> bool:
        """Check if a capability has a managed execution path."""
        base_path = (
            f"rhumb_managed_capabilities?capability_id=eq.{quote(capability_id)}"
            f"&enabled=eq.true&select=id&limit=1"
        )
        if not service_slug:
            rows = await supabase_fetch(base_path)
            return bool(rows)

        for candidate in self._service_slug_candidates(service_slug):
            rows = await supabase_fetch(
                f"{base_path}&service_slug=eq.{quote(candidate)}"
            )
            if rows:
                return True
        return False

    async def get_managed_config(
        self, capability_id: str, service_slug: str | None = None
    ) -> dict | None:
        """Fetch the managed capability config."""
        base_path = (
            f"rhumb_managed_capabilities?capability_id=eq.{quote(capability_id)}"
            f"&enabled=eq.true"
            f"&select=id,capability_id,service_slug,description,"
            f"credential_env_keys,default_method,default_path,default_headers,"
            f"daily_limit_per_agent&limit=1"
        )
        if not service_slug:
            rows = await supabase_fetch(base_path)
            return rows[0] if rows else None

        for candidate in self._service_slug_candidates(service_slug):
            rows = await supabase_fetch(
                f"{base_path}&service_slug=eq.{quote(candidate)}"
            )
            if rows:
                return rows[0]
        return None

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

        path_override, params, body = self._normalize_capability_inputs(
            capability_id,
            slug,
            params,
            body,
        )
        if path_override is not None:
            path = path_override

        # Path template interpolation: replace {param} with values from body or params.
        # Keys consumed by the path template are stripped from body/params so they
        # don't leak into the upstream JSON body or query string (e.g. Algolia
        # rejects unknown keys like ``indexName`` in the POST body).
        if "{" in path:
            import re as _re
            template_keys = set(_re.findall(r"\{(\w+)\}", path))
            sources = {**(params or {}), **(body or {})}
            missing_keys = [
                key for key in sorted(template_keys)
                if sources.get(key) in (None, "")
            ]
            if missing_keys:
                missing = ", ".join(missing_keys)
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required managed path parameter(s): {missing}",
                )
            for key in template_keys:
                path = path.replace(f"{{{key}}}", str(sources[key]))
            # Strip consumed template keys from body and params
            if body and template_keys:
                body = {k: v for k, v in body.items() if k not in template_keys}
            if params and template_keys:
                params = {k: v for k, v in params.items() if k not in template_keys}

        # For managed POST/PUT/PATCH flows, treat request.params as logical
        # capability inputs and merge them into the upstream JSON body.
        # Public examples (and the dogfood loop) already send capability inputs
        # via `params`, while providers like Tavily expect POST bodies.
        if method.upper() not in ("GET", "HEAD", "DELETE") and params:
            merged_body = dict(body) if body else {}
            for key, value in params.items():
                merged_body.setdefault(key, value)
            body = merged_body
            params = None

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

        multipart_data: list[tuple[str, str]] | None = None
        multipart_files: list[tuple[str, tuple[str, bytes, str]]] | None = None
        multipart_payload = self._extract_multipart_payload(slug, final_body)
        if multipart_payload is not None:
            multipart_data, multipart_files = multipart_payload
            final_body = None
            headers.pop("Content-Type", None)
            headers.pop("content-type", None)

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
                request_kwargs: dict[str, Any] = {
                    "method": method,
                    "url": path if path.startswith("/") else f"/{path}",
                    "headers": headers,
                    "params": params,
                }
                if multipart_files is not None:
                    # Merge form-data fields into the files list to avoid
                    # httpx AsyncClient sync/async multipart encoding conflict.
                    # Form fields become (field_name, (None, value_bytes)).
                    combined_files: list[tuple[str, tuple[str | None, bytes, str]]] = []
                    if multipart_data:
                        for field_name, field_value in multipart_data:
                            combined_files.append(
                                (field_name, (None, field_value.encode("utf-8"), "text/plain"))
                            )
                    combined_files.extend(multipart_files)
                    request_kwargs["files"] = combined_files
                else:
                    request_kwargs["json"] = final_body
                resp = await client.request(**request_kwargs)
                upstream_latency_ms = (time.perf_counter() - upstream_start) * 1000

            upstream_status = resp.status_code
            try:
                upstream_response = resp.json()
            except Exception:
                upstream_response = resp.text

            success = 200 <= upstream_status < 400

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

    @staticmethod
    def _rename_field(payload: dict | None, source_key: str, target_key: str) -> dict | None:
        if not payload or source_key not in payload or target_key in payload:
            return payload
        updated = dict(payload)
        updated[target_key] = updated.pop(source_key)
        return updated

    @staticmethod
    def _stringify_form_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return ""
        if isinstance(value, (int, float, str)):
            return str(value)
        return json.dumps(value)

    def _extract_multipart_payload(
        self,
        service_slug: str,
        body: dict | None,
    ) -> tuple[list[tuple[str, str]], list[tuple[str, tuple[str, bytes, str]]]] | None:
        """Convert JSON-native managed inputs into upstream multipart form data.

        Public execute remains JSON-shaped. Supported multipart providers currently
        include:

        - Unstructured: expects one or more ``files`` entries.
        - Mindee: expects a single ``document`` file on the legacy predict
          endpoints, but we also accept caller aliases like ``file`` and
          ``files`` for convenience.
        """
        if not body:
            return None

        if service_slug == "unstructured":
            file_keys = ("files",)
            default_field_name = "files"
        elif service_slug == "mindee":
            file_keys = ("document", "file", "files")
            default_field_name = "document"
        else:
            return None

        raw_files = next((body.get(key) for key in file_keys if key in body), None)
        if raw_files is None:
            return None

        file_descriptors = raw_files if isinstance(raw_files, list) else [raw_files]
        multipart_files: list[tuple[str, tuple[str, bytes, str]]] = []

        for descriptor in file_descriptors:
            if not isinstance(descriptor, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Managed multipart files must be objects",
                )

            field_name = (
                descriptor.get("field")
                or descriptor.get("field_name")
                or default_field_name
            )
            filename = descriptor.get("filename") or "upload.bin"
            content_type = (
                descriptor.get("content_type")
                or descriptor.get("contentType")
                or "application/octet-stream"
            )

            if descriptor.get("content_base64") is not None:
                try:
                    file_bytes = base64.b64decode(descriptor["content_base64"], validate=True)
                except Exception as exc:
                    raise HTTPException(
                        status_code=400,
                        detail="Managed multipart file content_base64 is invalid",
                    ) from exc
            elif descriptor.get("content") is not None:
                content = descriptor["content"]
                if isinstance(content, bytes):
                    file_bytes = content
                elif isinstance(content, str):
                    file_bytes = content.encode("utf-8")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Managed multipart file content must be bytes or string",
                    )
            elif descriptor.get("text") is not None:
                file_bytes = str(descriptor["text"]).encode("utf-8")
                if "content_type" not in descriptor and "contentType" not in descriptor:
                    content_type = "text/plain"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Managed multipart file descriptor requires content_base64, content, or text"
                    ),
                )

            multipart_files.append((field_name, (filename, file_bytes, content_type)))

        multipart_data: list[tuple[str, str]] = []
        for key, value in body.items():
            if key in file_keys or value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    multipart_data.append((key, self._stringify_form_value(item)))
            else:
                multipart_data.append((key, self._stringify_form_value(value)))

        return multipart_data, multipart_files

    @staticmethod
    def _is_truthy_flag(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _coerce_airship_channel_ids(
        channel_id: Any,
        channel_ids: Any,
    ) -> list[str]:
        raw_values = channel_ids if channel_ids is not None else channel_id
        if raw_values is None:
            return []
        if isinstance(raw_values, (list, tuple)):
            return [str(value) for value in raw_values if value is not None]
        return [str(raw_values)]

    @staticmethod
    def _build_airship_channel_audience(channel_ids: list[str]) -> dict[str, Any] | None:
        if not channel_ids:
            return None
        if len(channel_ids) == 1:
            return {"ios_channel": channel_ids[0]}
        return {"or": [{"ios_channel": channel_id} for channel_id in channel_ids]}

    @staticmethod
    def _uses_airship_ios_channel_audience(audience: Any) -> bool:
        if not isinstance(audience, dict):
            return False
        if "ios_channel" in audience:
            return True
        or_audience = audience.get("or")
        return isinstance(or_audience, list) and all(
            isinstance(item, dict) and "ios_channel" in item for item in or_audience
        )

    @staticmethod
    def _coerce_emailable_csv(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value if item is not None and str(item).strip()]
            return ",".join(items) if items else None
        text = str(value).strip()
        return text or None

    def _normalize_emailable_inputs(
        self,
        capability_id: str,
        params: dict | None,
        body: dict | None,
    ) -> tuple[str | None, dict | None, dict | None]:
        payload: dict[str, Any] = dict(params) if params else {}
        if body:
            payload.update(body)

        payload = self._rename_field(payload, "email_address", "email") or payload
        payload = self._rename_field(payload, "smtp_check", "smtp") or payload
        payload = self._rename_field(payload, "accept_all_check", "accept_all") or payload
        payload = self._rename_field(payload, "max_wait_seconds", "timeout") or payload
        payload = self._rename_field(payload, "callback_url", "url") or payload
        payload = self._rename_field(payload, "webhook_url", "url") or payload

        if capability_id == "email.batch_verify":
            emails_csv = self._coerce_emailable_csv(payload.get("emails"))
            if emails_csv is not None:
                payload["emails"] = emails_csv
            response_fields_csv = self._coerce_emailable_csv(payload.get("response_fields"))
            if response_fields_csv is not None:
                payload["response_fields"] = response_fields_csv

        return None, None, payload or None

    def _normalize_airship_inputs(
        self,
        capability_id: str,
        params: dict | None,
        body: dict | None,
    ) -> tuple[str | None, dict | None, dict | None]:
        payload: dict[str, Any] = dict(params) if params else {}
        if body:
            payload.update(body)

        validate_only = self._is_truthy_flag(payload.pop("validate_only", False))
        message = payload.pop("message", None)
        alert = payload.pop("alert", None)
        named_user_id = payload.pop("named_user_id", None)
        channel_id = payload.pop("channel_id", None)
        channel_ids = payload.pop("channel_ids", None)
        tag = payload.pop("tag", None)
        topic = payload.pop("topic", None)
        tag_group = payload.pop("tag_group", None)
        group = payload.pop("group", None)
        topic_group = payload.pop("topic_group", None)

        if payload.get("audience") is None:
            audience: dict[str, Any] | None = None
            if capability_id == "push_topic.publish":
                resolved_tag = tag if tag is not None else topic
                resolved_group = next(
                    (
                        value
                        for value in (tag_group, group, topic_group)
                        if value is not None
                    ),
                    None,
                )
                if resolved_tag is not None:
                    audience = {"tag": resolved_tag}
                    if resolved_group is not None:
                        audience["group"] = resolved_group

            if audience is None and named_user_id is not None:
                audience = {"named_user": named_user_id}

            if audience is None:
                audience = self._build_airship_channel_audience(
                    self._coerce_airship_channel_ids(channel_id, channel_ids)
                )

            if audience is not None:
                payload["audience"] = audience

        if payload.get("notification") is None:
            resolved_alert = message if message is not None else alert
            if resolved_alert is not None:
                payload["notification"] = {"alert": resolved_alert}

        if (
            "device_types" not in payload
            and self._uses_airship_ios_channel_audience(payload.get("audience"))
        ):
            payload["device_types"] = ["ios"]

        path_override = "/api/push/validate" if validate_only else None
        return path_override, None, payload or None

    def _normalize_capability_inputs(
        self,
        capability_id: str,
        service_slug: str,
        params: dict | None,
        body: dict | None,
    ) -> tuple[str | None, dict | None, dict | None]:
        """Map logical capability inputs to provider-native fields."""
        path_override: str | None = None

        if service_slug == "airship" and capability_id in {
            "push_notification.send",
            "push_notification.send_to_user",
            "push_topic.publish",
        }:
            return self._normalize_airship_inputs(capability_id, params, body)

        if service_slug == "emailable" and capability_id in {
            "email.verify",
            "email.batch_verify",
        }:
            return self._normalize_emailable_inputs(capability_id, params, body)

        if service_slug == "mindee" and capability_id in {
            "document.extract_fields",
            "invoice.extract",
        }:
            payload: dict[str, Any] = dict(params) if params else {}
            if body:
                payload.update(body)
            payload = self._rename_field(payload, "file", "document") or payload
            payload = self._rename_field(payload, "files", "document") or payload
            return None, None, payload or None

        if service_slug == "algolia" and capability_id in {
            "search.index",
            "search.autocomplete",
            "ecommerce.search_products",
            "document.search",
        }:
            params = self._rename_field(params, "index", "indexName")
            body = self._rename_field(body, "index", "indexName")
            params = self._rename_field(params, "index_name", "indexName")
            body = self._rename_field(body, "index_name", "indexName")

        if service_slug == "brave-search" and capability_id in {"search.query", "search.web_search"}:
            params = self._rename_field(params, "query", "q")
            body = self._rename_field(body, "query", "q")
            params = self._rename_field(params, "numResults", "count")
            body = self._rename_field(body, "numResults", "count")
            params = self._rename_field(params, "num_results", "count")
            body = self._rename_field(body, "num_results", "count")
        return path_override, params, body

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
        "e2b": ("X-API-Key", None),
        # Token auth (non-Bearer Authorization header)
        "deepgram": ("Authorization", "Token "),
        "mindee": ("Authorization", "Token "),
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
