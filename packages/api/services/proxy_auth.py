"""Auth injection logic for the proxy service.

Injects the correct ``Authorization`` header for each supported provider
based on credentials fetched from the :class:`CredentialStore`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from services.proxy_credentials import CredentialStore, get_credential_store


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
    """Describes a pending auth-header injection."""

    service: str  # "stripe", "slack", etc.
    agent_id: str
    auth_method: AuthMethod
    existing_headers: Dict[str, str] = field(default_factory=dict)


class AuthInjector:
    """Inject ``Authorization`` headers for different providers."""

    # Per-provider auth patterns.
    AUTH_PATTERNS: Dict[str, Dict[str, object]] = {
        "stripe": {
            "methods": ["api_key"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
        "slack": {
            "methods": ["oauth_token", "app_token"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
        "github": {
            "methods": ["api_token"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
        "twilio": {
            "methods": ["basic_auth"],
            "header": "Authorization",
            "format": "Basic {credential}",
        },
        "sendgrid": {
            "methods": ["api_key"],
            "header": "Authorization",
            "format": "Bearer {credential}",
        },
    }

    def __init__(self, credential_store: CredentialStore) -> None:
        self.credentials = credential_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(self, request: AuthInjectionRequest) -> Dict[str, str]:
        """Inject the auth header into *request.existing_headers*.

        Args:
            request: Contains the service, agent_id, auth_method, and
                existing headers to augment.

        Returns:
            A **new** headers dict with the ``Authorization`` header set.

        Raises:
            ValueError: If service or auth method is unsupported.
            RuntimeError: If the credential cannot be found in the store.
        """
        service = request.service
        auth_method = request.auth_method

        if service not in self.AUTH_PATTERNS:
            raise ValueError(
                f"Service '{service}' not supported. "
                f"Available: {', '.join(self.AUTH_PATTERNS)}"
            )

        pattern = self.AUTH_PATTERNS[service]
        allowed_methods: list[str] = pattern["methods"]  # type: ignore[assignment]
        if auth_method.value not in allowed_methods:
            raise ValueError(
                f"Auth method '{auth_method.value}' not supported for '{service}'. "
                f"Supported: {allowed_methods}"
            )

        # Retrieve credential
        credential = self.credentials.get_credential(service, auth_method.value)
        if credential is None:
            raise RuntimeError(
                f"Credential not found for {service}/{auth_method.value}"
            )

        # For Twilio basic-auth the credential value is "account_sid:auth_token".
        # We must base64-encode it before injection.
        if auth_method == AuthMethod.BASIC_AUTH:
            credential = base64.b64encode(credential.encode()).decode()

        fmt: str = pattern["format"]  # type: ignore[assignment]
        formatted = fmt.format(credential=credential)

        headers = request.existing_headers.copy()
        header_name: str = pattern["header"]  # type: ignore[assignment]
        headers[header_name] = formatted

        # Audit
        self.credentials.audit_log(service, request.agent_id, "auth_injected")

        return headers

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


def get_auth_injector() -> AuthInjector:
    """Return (or create) the global :class:`AuthInjector` singleton."""
    global _injector
    if _injector is None:
        _injector = AuthInjector(get_credential_store())
    return _injector
