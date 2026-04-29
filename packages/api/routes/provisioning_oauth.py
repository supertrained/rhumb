"""OAuth 2.0 provisioning flow — consent + code exchange + token storage.

Handles the full OAuth authorization-code flow:
1. Agent requests OAuth for a service with desired scopes
2. Handler builds the authorization URL (consent screen)
3. Human visits the URL, grants consent
4. Provider redirects to callback with ``code`` + ``state``
5. Handler exchanges code for access token
6. Token is stored in the credential store

No blocking waits — the consent URL is returned immediately.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from schemas.provisioning import (
    FlowState,
    FlowType,
    ProvisioningFlowStore,
)
from services.proxy_credentials import CredentialStore
from services.service_slugs import public_service_slug


# OAuth provider metadata
_OAUTH_ENDPOINTS: Dict[str, Dict[str, str]] = {
    "slack": {
        "authorize": "https://slack.com/oauth/v2/authorize",
        "token": "https://slack.com/api/oauth.v2.access",
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
    },
    "stripe": {
        "authorize": "https://connect.stripe.com/oauth/authorize",
        "token": "https://connect.stripe.com/oauth/token",
    },
}

# In-memory state token store (maps state_token → flow_id)
_state_tokens: Dict[str, str] = {}

# Default redirect base
_REDIRECT_BASE = "https://api.rhumb.dev"


class OAuthFlowHandler:
    """OAuth 2.0 authorization flow for agent provisioning."""

    def __init__(
        self,
        store: ProvisioningFlowStore,
        credential_store: Optional[CredentialStore] = None,
        *,
        redirect_base: str = _REDIRECT_BASE,
    ) -> None:
        self.store = store
        self.credential_store = credential_store
        self.redirect_base = redirect_base

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start_oauth(
        self,
        agent_id: str,
        service: str,
        scopes: List[str],
    ) -> Dict[str, Any]:
        """Start an OAuth authorization flow.

        Returns:
            ``{"flow_id", "authorization_url", "expires_in"}``
        """
        public_service = public_service_slug(service) or str(service).strip().lower()

        if public_service not in _OAUTH_ENDPOINTS:
            return {
                "flow_id": None,
                "status": "failed",
                "error": f"Service '{public_service}' does not support OAuth flows",
            }

        # Create flow
        flow_id = await self.store.create_flow(
            agent_id=agent_id,
            service=public_service,
            flow_type=FlowType.OAUTH,
            payload={"scopes": scopes},
            ttl_hours=1,  # OAuth consent URLs are short-lived
        )

        # Build authorization URL
        auth_url = self._build_oauth_url(public_service, flow_id, scopes)
        await self.store.set_human_action_url(flow_id, auth_url)

        return {
            "flow_id": flow_id,
            "authorization_url": auth_url,
            "expires_in": 3600,
        }

    # ------------------------------------------------------------------
    # Callback
    # ------------------------------------------------------------------

    async def handle_callback(
        self,
        flow_id: str,
        code: str,
        state: str,
    ) -> Dict[str, Any]:
        """Handle the OAuth provider callback after the human grants consent.

        Args:
            flow_id: The flow ID embedded in the redirect URI.
            code: Authorization code from the provider.
            state: State token for CSRF verification.

        Returns:
            ``{"status", "message"}`` or ``{"status", "error"}``.
        """
        normalized_flow_id = str(flow_id or "").strip()
        if not normalized_flow_id:
            return {"status": "failed", "error": "flow_id required"}
        normalized_code = str(code or "").strip()
        if not normalized_code:
            return {"status": "failed", "error": "code required"}
        normalized_state = str(state or "").strip()
        if not normalized_state:
            return {"status": "failed", "error": "state required"}

        flow = await self.store.get_flow(normalized_flow_id)
        if flow is None:
            return {"status": "failed", "error": "flow_not_found"}

        # Check expiration
        if await self.store.check_expiration(normalized_flow_id):
            return {"status": "failed", "error": "flow_expired"}

        # Verify state token
        if not self._verify_state(normalized_state, normalized_flow_id):
            return {"status": "failed", "error": "invalid_state"}

        # Exchange code for token
        try:
            token_response = await self._exchange_code(flow.service, normalized_code, normalized_flow_id)
            access_token = token_response.get("access_token", "")

            if not access_token:
                raise ValueError("No access_token in response")

            # Store token in credential store
            if self.credential_store is not None:
                expires_in = token_response.get("expires_in", 3600)
                self.credential_store.set_credential(
                    service=flow.service,
                    key="oauth_token",
                    value=access_token,
                    expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
                )

            # Mark flow complete
            await self.store.update_flow_state(
                normalized_flow_id,
                FlowState.COMPLETE,
                callback_data={
                    "token_type": token_response.get("token_type", "bearer"),
                    "scope": token_response.get("scope", ""),
                },
            )

            return {"status": "complete", "message": "OAuth token stored"}

        except Exception as e:
            # Increment retries
            retries = await self.store.increment_retries(normalized_flow_id)
            flow_fresh = await self.store.get_flow(normalized_flow_id)
            max_retries = flow_fresh.max_retries if flow_fresh else 3

            if retries >= max_retries:
                await self.store.update_flow_state(
                    normalized_flow_id,
                    FlowState.FAILED,
                    error_message=f"Max retries exceeded: {e}",
                )
                return {"status": "failed", "error": f"max_retries_exceeded: {e}"}

            return {"status": "retry", "error": str(e), "retries": retries}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_oauth_url(
        self, service: str, flow_id: str, scopes: List[str]
    ) -> str:
        """Build the OAuth consent URL for the given service."""
        endpoints = _OAUTH_ENDPOINTS[service]
        state_token = self._generate_state_token(flow_id)

        params = {
            "client_id": self._get_client_id(service),
            "redirect_uri": f"{self.redirect_base}/oauth/callback/{flow_id}",
            "scope": " ".join(scopes),
            "state": state_token,
            "response_type": "code",
        }

        return f"{endpoints['authorize']}?{urlencode(params)}"

    def _generate_state_token(self, flow_id: str) -> str:
        """Generate and store a CSRF state token for the flow."""
        token = secrets.token_urlsafe(32)
        _state_tokens[token] = flow_id
        return token

    def _verify_state(self, state: str, flow_id: str) -> bool:
        """Verify the state token matches the expected flow."""
        expected_flow = _state_tokens.get(state)
        if expected_flow is None:
            return False
        return expected_flow == flow_id

    @staticmethod
    def _get_client_id(service: str) -> str:
        """Retrieve the OAuth client ID for a service.

        In production this reads from 1Password.  For now returns a
        placeholder to avoid blocking on secrets availability.
        """
        client_ids: Dict[str, str] = {
            "slack": "SLACK_CLIENT_ID",
            "github": "GITHUB_CLIENT_ID",
            "stripe": "STRIPE_CLIENT_ID",
        }
        return client_ids.get(service, f"{service.upper()}_CLIENT_ID")

    async def _exchange_code(
        self, service: str, code: str, flow_id: str
    ) -> Dict[str, Any]:
        """Exchange an authorization code for an access token.

        In production this makes an HTTP POST to the provider's token
        endpoint.  For now it returns a mock token response to allow
        the full flow to be tested end-to-end without live providers.
        """
        # Mock token exchange (replaced with real HTTP in production)
        return {
            "access_token": f"mock_access_token_{service}_{flow_id[:8]}",
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": "read write",
        }
