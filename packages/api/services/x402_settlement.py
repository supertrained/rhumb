"""x402 settlement service — local EIP-3009 + facilitator fallback.

Rhumb supports two settlement paths for standard x402 authorization payloads:

1. **Local settlement** (preferred) — Rhumb verifies the EIP-3009 signature
   off-chain, then submits ``transferWithAuthorization`` on Base mainnet.
   Requires ``RHUMB_SETTLEMENT_PRIVATE_KEY``.

2. **Facilitator settlement** (fallback) — Forward the authorization payload
   to an x402 facilitator's ``/verify`` and ``/settle`` endpoints.
   Requires ``X402_FACILITATOR_URL``.

When both are configured, local settlement is tried first.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import httpx

from services.x402_local_settlement import (
    LocalX402Settlement,
    SettlementOnChainFailed,
    SettlementVerificationFailed,
)

logger = logging.getLogger(__name__)


class X402FacilitatorError(RuntimeError):
    """Base facilitator error."""


class X402FacilitatorNotConfigured(X402FacilitatorError):
    """Raised when no settlement path (local or facilitator) is configured."""


class X402VerificationFailed(X402FacilitatorError):
    """Raised when payment verification rejects the payload."""


class X402SettlementFailed(X402FacilitatorError):
    """Raised when payment settlement fails."""


class X402SettlementService:
    """Unified settlement service: local EIP-3009 first, facilitator fallback.

    The ``verify_and_settle`` method returns a consistent dict shape regardless
    of which settlement path is used::

        {
            "verify": {...},
            "settle": {...},
            "payer": "0x...",
            "transaction": "0xhash",
            "network": "base",
            "payment_response_header": "<base64>",
        }
    """

    def __init__(self, timeout_seconds: float = 30.0):
        self._timeout_seconds = timeout_seconds
        self._local = LocalX402Settlement()

    # ── Configuration ─────────────────────────────────────────────────

    def facilitator_url(self) -> str | None:
        url = (
            os.environ.get("X402_FACILITATOR_URL")
            or os.environ.get("RHUMB_X402_FACILITATOR_URL")
            or ""
        ).strip()
        return url.rstrip("/") or None

    def is_configured(self) -> bool:
        """Return True if at least one settlement path is available."""
        return self._local.is_configured() or self.facilitator_url() is not None

    def local_configured(self) -> bool:
        return self._local.is_configured()

    def facilitator_configured(self) -> bool:
        return self.facilitator_url() is not None

    # ── Unified entry point ───────────────────────────────────────────

    async def verify_and_settle(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify and settle a standard x402 authorization payload.

        Tries facilitator first (handles all wallet types including smart wallets),
        falls back to local EIP-3009 settlement for simple EOA signatures.
        Raises ``X402FacilitatorNotConfigured`` if neither path is available.
        """
        # Try facilitator first — it handles all signature types robustly
        if self.facilitator_url() is not None:
            try:
                result = await self._facilitator_verify_and_settle(
                    payment_payload, payment_requirements
                )
                logger.info(
                    "x402 facilitator settlement succeeded tx=%s payer=%s",
                    result.get("transaction"),
                    result.get("payer"),
                )
                return result
            except (X402VerificationFailed, X402SettlementFailed) as e:
                # Facilitator rejected — definitive failure, don't retry locally
                raise
            except X402FacilitatorError as e:
                # Facilitator infrastructure error — fall back to local if available
                if self._local.is_configured():
                    logger.warning(
                        "Facilitator error (%s); falling back to local settlement", e
                    )
                else:
                    raise X402SettlementFailed(str(e)) from e

        # Local settlement fallback (EOA signatures only)
        if self._local.is_configured():
            try:
                result = await self._local.verify_and_settle(
                    payment_payload, payment_requirements
                )
                logger.info(
                    "x402 local settlement succeeded tx=%s payer=%s",
                    result.get("transaction"),
                    result.get("payer"),
                )
                return result
            except SettlementVerificationFailed as e:
                raise X402VerificationFailed(str(e)) from e
            except SettlementOnChainFailed as e:
                raise X402SettlementFailed(str(e)) from e

        raise X402FacilitatorNotConfigured(
            "No x402 settlement path configured (need X402_FACILITATOR_URL "
            "or RHUMB_SETTLEMENT_PRIVATE_KEY)"
        )

    # ── Facilitator path (preserved from original) ────────────────────

    def _headers_for(self, operation: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        auth_value = (
            os.environ.get(f"X402_FACILITATOR_{operation.upper()}_AUTHORIZATION")
            or os.environ.get("X402_FACILITATOR_AUTHORIZATION")
            or os.environ.get(f"RHUMB_X402_FACILITATOR_{operation.upper()}_AUTHORIZATION")
            or os.environ.get("RHUMB_X402_FACILITATOR_AUTHORIZATION")
            or ""
        ).strip()
        if auth_value:
            headers["Authorization"] = auth_value
        return headers

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return json.loads(
            json.dumps(
                value,
                default=lambda x: str(x) if isinstance(x, int) and x > 2**53 else x,
            )
        )

    def _request_body(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        version = int(payment_payload.get("x402Version") or 1)
        return {
            "x402Version": version,
            "paymentPayload": self._json_safe(payment_payload),
            "paymentRequirements": self._json_safe(payment_requirements),
        }

    async def _post(self, operation: str, body: dict[str, Any]) -> dict[str, Any]:
        facilitator_url = self.facilitator_url()
        if facilitator_url is None:
            raise X402FacilitatorNotConfigured(
                "No x402 facilitator URL configured for standard authorization settlement"
            )

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{facilitator_url}/{operation}",
                headers=self._headers_for(operation),
                json=body,
            )

        try:
            data = response.json()
        except Exception as exc:  # pragma: no cover - defensive
            raise X402FacilitatorError(
                f"Facilitator {operation} returned invalid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise X402FacilitatorError(
                f"Facilitator {operation} returned a non-object response"
            )

        return {"status_code": response.status_code, "data": data}

    async def verify(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        result = await self._post(
            "verify",
            self._request_body(payment_payload, payment_requirements),
        )
        status_code = result["status_code"]
        data = result["data"]

        if status_code >= 400:
            raise X402VerificationFailed(
                data.get("invalidMessage")
                or data.get("invalidReason")
                or f"Facilitator verify failed ({status_code})"
            )

        if not isinstance(data.get("isValid"), bool):
            raise X402FacilitatorError("Facilitator verify response missing isValid")

        if not data.get("isValid"):
            raise X402VerificationFailed(
                data.get("invalidMessage") or data.get("invalidReason") or "Payment proof rejected"
            )

        return data

    async def settle(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        result = await self._post(
            "settle",
            self._request_body(payment_payload, payment_requirements),
        )
        status_code = result["status_code"]
        data = result["data"]

        if status_code >= 400:
            raise X402SettlementFailed(
                data.get("errorMessage")
                or data.get("errorReason")
                or f"Facilitator settle failed ({status_code})"
            )

        if not isinstance(data.get("success"), bool):
            raise X402FacilitatorError("Facilitator settle response missing success")

        if not data.get("success"):
            raise X402SettlementFailed(
                data.get("errorMessage") or data.get("errorReason") or "Payment settlement failed"
            )

        transaction = data.get("transaction")
        network = data.get("network")
        if not transaction or not network:
            raise X402FacilitatorError(
                "Facilitator settle response missing transaction or network"
            )

        return data

    async def _facilitator_verify_and_settle(
        self,
        payment_payload: dict[str, Any],
        payment_requirements: dict[str, Any],
    ) -> dict[str, Any]:
        verify_response = await self.verify(payment_payload, payment_requirements)
        settle_response = await self.settle(payment_payload, payment_requirements)
        payment_response_header = base64.b64encode(
            json.dumps(settle_response, separators=(",", ":")).encode("utf-8")
        ).decode("utf-8")
        return {
            "verify": verify_response,
            "settle": settle_response,
            "payer": settle_response.get("payer") or verify_response.get("payer"),
            "transaction": settle_response["transaction"],
            "network": settle_response["network"],
            "payment_response_header": payment_response_header,
        }
