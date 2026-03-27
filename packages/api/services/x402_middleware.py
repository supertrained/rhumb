"""x402 payment middleware — extracts and classifies X-Payment header values.

Rhumb currently supports a legacy payment proof shape built around an
on-chain USDC transfer receipt:

    tx_hash:              On-chain transaction hash
    network:              ``"base"`` | ``"base-sepolia"`` (also accepts
                          ``"evm:8453"`` | ``"evm:84532"`` | legacy
                          ``"base-mainnet"``)
    payment_request_id:   (optional) Links back to a prior 402 response

Some buyers now send the standard x402 authorization payload instead:

    {
      "x402Version": 1,
      "scheme": "exact",
      "network": "base",
      "payload": {
        "authorization": {"from": "...", "to": "...", ...},
        "signature": "..."
      }
    }

This module decodes both shapes and exposes proof-format metadata so the
route layer can produce truthful compatibility responses.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


_STANDARD_X402_TOP_LEVEL_KEYS = {"x402Version", "scheme", "network", "payload"}


def describe_x_payment_payload(payment_data: dict[str, Any] | None) -> dict[str, Any]:
    """Return normalized proof-shape metadata for a decoded payment payload."""
    if not isinstance(payment_data, dict):
        return {
            "proof_format": "unknown",
            "declared_network": None,
            "declared_scheme": None,
            "declared_from": None,
            "declared_to": None,
        }

    if payment_data.get("tx_hash"):
        return {
            "proof_format": "legacy_tx_hash",
            "declared_network": payment_data.get("network"),
            "declared_scheme": None,
            "declared_from": payment_data.get("wallet_address") or payment_data.get("from"),
            "declared_to": None,
        }

    payload = payment_data.get("payload")
    authorization = payload.get("authorization") if isinstance(payload, dict) else None
    if (
        _STANDARD_X402_TOP_LEVEL_KEYS.issubset(payment_data.keys())
        and isinstance(authorization, dict)
    ):
        return {
            "proof_format": "standard_authorization_payload",
            "declared_network": payment_data.get("network"),
            "declared_scheme": payment_data.get("scheme"),
            "declared_from": authorization.get("from"),
            "declared_to": authorization.get("to"),
        }

    return {
        "proof_format": "unknown",
        "declared_network": payment_data.get("network"),
        "declared_scheme": payment_data.get("scheme"),
        "declared_from": payment_data.get("from") or payment_data.get("wallet_address"),
        "declared_to": payment_data.get("to"),
    }


def inspect_x_payment_header(header_value: str | None) -> dict[str, Any]:
    """Decode and classify an ``X-Payment`` header value.

    Returns a small inspection payload for observability and branch tracing:

    - ``payment_data``: decoded dict or ``None``
    - ``parse_mode``: ``missing`` | ``invalid`` | ``raw_json`` | ``base64_json`` | ``x402_payload``
    - ``top_level_keys``: sorted list of decoded top-level keys
    """
    if not header_value or not header_value.strip():
        return {
            "payment_data": None,
            "parse_mode": "missing",
            "top_level_keys": [],
            **describe_x_payment_payload(None),
        }

    # Try base64 first.
    try:
        decoded_bytes = base64.b64decode(header_value, validate=True)
        payment_data = json.loads(decoded_bytes)
        parse_mode = "base64_json"
        if isinstance(payment_data, dict) and _STANDARD_X402_TOP_LEVEL_KEYS.issubset(payment_data.keys()):
            parse_mode = "x402_payload"
        return {
            "payment_data": payment_data if isinstance(payment_data, dict) else None,
            "parse_mode": parse_mode,
            "top_level_keys": sorted(payment_data.keys()) if isinstance(payment_data, dict) else [],
            **describe_x_payment_payload(payment_data if isinstance(payment_data, dict) else None),
        }
    except Exception:
        pass

    # Try raw JSON.
    try:
        payment_data = json.loads(header_value)
        parse_mode = "raw_json"
        if isinstance(payment_data, dict) and _STANDARD_X402_TOP_LEVEL_KEYS.issubset(payment_data.keys()):
            parse_mode = "x402_payload"
        return {
            "payment_data": payment_data if isinstance(payment_data, dict) else None,
            "parse_mode": parse_mode,
            "top_level_keys": sorted(payment_data.keys()) if isinstance(payment_data, dict) else [],
            **describe_x_payment_payload(payment_data if isinstance(payment_data, dict) else None),
        }
    except Exception as e:
        logger.warning("Failed to decode X-Payment header: %s", e)
        return {
            "payment_data": None,
            "parse_mode": "invalid",
            "top_level_keys": [],
            **describe_x_payment_payload(None),
        }


def decode_x_payment_header(header_value: str) -> Optional[dict]:
    """Decode the ``X-Payment`` header value.

    Supports two encodings:

    1. **Base64-encoded JSON** — the client base64-encodes the JSON payload.
    2. **Raw JSON** — the client sends JSON directly.

    Returns the decoded dict or ``None`` if decoding fails.
    """
    return inspect_x_payment_header(header_value).get("payment_data")
