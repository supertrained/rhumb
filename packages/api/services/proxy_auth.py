"""Auth injection logic for proxy-capable providers.

Injects provider credentials into the correct request part, for example a
header, query parameter, or JSON body field, based on credentials fetched from
the :class:`CredentialStore`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional

from services.proxy_credentials import CredentialStore, get_credential_store

if TYPE_CHECKING:
    from services.operational_fact_emitter import OperationalFactEmitter


class AuthMethod(str, Enum):
    """Supported authentication methods."""

    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH_TOKEN = "oauth_token"
    API_TOKEN = "api_token"
    APP_TOKEN = "app_token"


@dataclass
class AuthInjectionRequest:
    """Describes a pending provider-auth injection."""

    service: str  # "stripe", "slack", etc.
    agent_id: str
    auth_method: AuthMethod
    existing_headers: Dict[str, str] = field(default_factory=dict)
    existing_params: Dict[str, Any] = field(default_factory=dict)
    existing_body: Optional[Dict[str, Any]] = None


@dataclass
class AuthInjectionResult:
    """Result of applying provider auth to request parts."""

    headers: Dict[str, str]
    params: Dict[str, Any]
    body: Optional[Dict[str, Any]]


class AuthInjector:
    """Inject provider auth into request headers, params, or body."""

    # Per-provider auth patterns.
    AUTH_PATTERNS: Dict[str, Dict[str, object]] = {
        "stripe": {
            "methods": ["api_key"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "slack": {
            "methods": ["oauth_token", "app_token"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "github": {
            "methods": ["api_token"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "twilio": {
            "methods": ["basic_auth"],
            "target": "header",
            "name": "Authorization",
            "format": "Basic {credential}",
        },
        "sendgrid": {
            "methods": ["api_key"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "firecrawl": {
            "methods": ["api_key"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "apify": {
            "methods": ["api_token"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "apollo": {
            "methods": ["api_key"],
            "target": "header",
            "name": "X-Api-Key",
            "format": "{credential}",
        },
        "pdl": {
            "methods": ["api_key"],
            "target": "header",
            "name": "X-API-Key",
            "format": "{credential}",
        },
        "tavily": {
            "methods": ["api_key"],
            "target": "body",
            "name": "api_key",
            "format": "{credential}",
        },
        "exa": {
            "methods": ["api_key"],
            "target": "header",
            "name": "x-api-key",
            "format": "{credential}",
        },
        "brave-search": {
            "methods": ["api_key"],
            "target": "header",
            "name": "X-Subscription-Token",
            "format": "{credential}",
        },
        "replicate": {
            "methods": ["api_token"],
            "target": "header",
            "name": "Authorization",
            "format": "Bearer {credential}",
        },
        "algolia": {
            "methods": ["api_key"],
            "target": "header",
            "name": "X-Algolia-API-Key",
            "format": "{credential}",
        },
        "e2b": {
            "methods": ["api_key"],
            "target": "header",
            "name": "X-API-Key",
            "format": "{credential}",
        },
        "unstructured": {
            "methods": ["api_key"],
            "target": "header",
            "name": "unstructured-api-key",
            "format": "{credential}",
        },
        "google-ai": {
            "methods": ["api_key"],
            "target": "header",
            "name": "x-goog-api-key",
            "format": "{credential}",
        },
        "ipinfo": {
            "methods": ["bearer_token"],
            "target": "query",
            "name": "token",
            "format": "{credential}",
        },
        "scraperapi": {
            "methods": ["api_key"],
            "target": "query",
            "name": "api_key",
            "format": "{credential}",
        },
        "deepgram": {
            "methods": ["api_key"],
            "target": "header",
            "name": "Authorization",
            "format": "Token {credential}",
        },
    }

    def __init__(
        self,
        credential_store: CredentialStore,
        emitter: Optional["OperationalFactEmitter"] = None,
    ) -> None:
        self.credentials = credential_store
        self._emitter = emitter

    @property
    def emitter(self) -> "OperationalFactEmitter":
        if self._emitter is None:
            from services.operational_fact_emitter import get_operational_fact_emitter

            self._emitter = get_operational_fact_emitter()
        return self._emitter

    @emitter.setter
    def emitter(self, value: "OperationalFactEmitter") -> None:
        self._emitter = value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(self, request: AuthInjectionRequest) -> Dict[str, str]:
        """Inject auth into headers for header-based services.

        Args:
            request: Contains the service, agent_id, auth_method, and
                existing headers to augment.

        Returns:
            A **new** headers dict with the auth header set.

        Raises:
            ValueError: If service or auth method is unsupported, or when the
                provider requires auth in params/body instead of headers.
            RuntimeError: If the credential cannot be found in the store.
        """
        pattern = self.AUTH_PATTERNS.get(request.service)
        if pattern is not None and pattern.get("target", "header") != "header":
            raise ValueError(
                f"Service '{request.service}' requires non-header auth injection; "
                "use inject_request_parts()"
            )
        return self.inject_request_parts(request).headers

    def inject_request_parts(self, request: AuthInjectionRequest) -> AuthInjectionResult:
        """Inject provider auth into request headers, params, or body."""
        service = request.service
        auth_method = request.auth_method
        injection_name: Optional[str] = None

        if service not in self.AUTH_PATTERNS:
            error = ValueError(
                f"Service '{service}' not supported. "
                f"Available: {', '.join(self.AUTH_PATTERNS)}"
            )
            self._emit_credential_lifecycle(
                request,
                event_type="credential_lookup_failed",
                outcome="error",
                error=error,
            )
            raise error

        pattern = self.AUTH_PATTERNS[service]
        allowed_methods: list[str] = pattern["methods"]  # type: ignore[assignment]
        injection_name = pattern["name"]  # type: ignore[assignment]
        if auth_method.value not in allowed_methods:
            error = ValueError(
                f"Auth method '{auth_method.value}' not supported for '{service}'. "
                f"Supported: {allowed_methods}"
            )
            self._emit_credential_lifecycle(
                request,
                event_type="credential_lookup_failed",
                outcome="error",
                header_name=injection_name,
                error=error,
            )
            raise error

        # Retrieve credential
        try:
            credential = self.credentials.get_credential(service, auth_method.value)
        except Exception as error:
            self._emit_credential_lifecycle(
                request,
                event_type="credential_lookup_failed",
                outcome="error",
                header_name=injection_name,
                error=error,
            )
            raise
        if credential is None:
            error = RuntimeError(
                f"Credential not found for {service}/{auth_method.value}"
            )
            self._emit_credential_lifecycle(
                request,
                event_type="credential_missing",
                outcome="missing",
                header_name=injection_name,
                error=error,
            )
            raise error

        # For Twilio basic-auth the credential value is "account_sid:auth_token".
        # We must base64-encode it before injection.
        if auth_method == AuthMethod.BASIC_AUTH:
            credential = base64.b64encode(credential.encode()).decode()

        fmt: str = pattern["format"]  # type: ignore[assignment]
        formatted = fmt.format(credential=credential)

        headers = request.existing_headers.copy()
        params = request.existing_params.copy()
        body = request.existing_body.copy() if request.existing_body is not None else None

        target = pattern.get("target", "header")
        assert injection_name is not None
        if target == "header":
            headers[injection_name] = formatted
        elif target == "query":
            params[injection_name] = formatted
        elif target == "body":
            if body is None:
                body = {}
            body[injection_name] = formatted
        else:
            error = ValueError(f"Unsupported auth injection target '{target}' for '{service}'")
            self._emit_credential_lifecycle(
                request,
                event_type="credential_lookup_failed",
                outcome="error",
                header_name=injection_name,
                error=error,
            )
            raise error

        # Audit
        self.credentials.audit_log(service, request.agent_id, "auth_injected")
        self._emit_credential_lifecycle(
            request,
            event_type="credential_injected",
            outcome="success",
            header_name=injection_name,
        )

        return AuthInjectionResult(headers=headers, params=params, body=body)

    def _emit_credential_lifecycle(
        self,
        request: AuthInjectionRequest,
        *,
        event_type: str,
        outcome: str,
        header_name: str | None = None,
        error: Exception | None = None,
    ) -> None:
        error_type = type(error).__name__ if error is not None else None
        self.emitter.schedule_credential_lifecycle(
            service=request.service,
            agent_id=request.agent_id,
            event_type=event_type,
            auth_method=request.auth_method.value,
            header_name=header_name,
            outcome=outcome,
            error_type=error_type,
            error_message=self._sanitize_error_message(error),
        )

    @staticmethod
    def _sanitize_error_message(error: Exception | None) -> str | None:
        if error is None:
            return None
        if isinstance(error, RuntimeError):
            return "credential not found"
        if isinstance(error, ValueError):
            message = str(error)
            if "not supported" in message and "Service" in message:
                return "service not supported"
            if "not supported" in message and "Auth method" in message:
                return "auth method not supported"
        return "credential lookup failed"

    # ------------------------------------------------------------------
    # Convenience: determine default auth method for a service
    # ------------------------------------------------------------------

    @classmethod
    def default_method_for(cls, service: str) -> Optional[AuthMethod]:
        """Return the first supported :class:`AuthMethod` for *service*."""
        pattern = cls.AUTH_PATTERNS.get(service)
        if pattern is None:
            return None
        methods: list[str] = pattern["methods"]  # type: ignore[assignment]
        if not methods:
            return None
        return AuthMethod(methods[0])


# ------------------------------------------------------------------
# Singleton accessor
# ------------------------------------------------------------------

_injector: Optional[AuthInjector] = None


def get_auth_injector(
    emitter: Optional["OperationalFactEmitter"] = None,
) -> AuthInjector:
    """Return (or create) the global :class:`AuthInjector` singleton."""
    global _injector
    if _injector is None:
        _injector = AuthInjector(get_credential_store(), emitter=emitter)
    elif emitter is not None:
        _injector.emitter = emitter
    return _injector
