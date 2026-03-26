"""x402 payment middleware — extracts and validates X-Payment header.

When a client attaches an ``X-Payment`` header to an execute request it
contains a JSON payload (base64-encoded or raw JSON) with at minimum:

    tx_hash:              On-chain transaction hash
    network:              ``"base"`` | ``"base-sepolia"`` (also accepts ``"evm:8453"`` | ``"evm:84532"`` | legacy ``"base-mainnet"``)
    payment_request_id:   (optional) Links back to a prior 402 response
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


_STANDARD_X402_TOP_LEVEL_KEYS = {"x402Version", "scheme", "network", "payload"}


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
        }
    except Exception as e:
        logger.warning("Failed to decode X-Payment header: %s", e)
        return {
            "payment_data": None,
            "parse_mode": "invalid",
            "top_level_keys": [],
        }


def decode_x_payment_header(header_value: str) -> Optional[dict]:
    """Decode the ``X-Payment`` header value.

    Supports two encodings:

    1. **Base64-encoded JSON** — the client base64-encodes the JSON payload.
    2. **Raw JSON** — the client sends JSON directly.

    Returns the decoded dict or ``None`` if decoding fails.
    """
    return inspect_x_payment_header(header_value).get("payment_data")
