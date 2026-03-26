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
from typing import Optional

logger = logging.getLogger(__name__)


def decode_x_payment_header(header_value: str) -> Optional[dict]:
    """Decode the ``X-Payment`` header value.

    Supports two encodings:

    1. **Base64-encoded JSON** — the client base64-encodes the JSON payload.
    2. **Raw JSON** — the client sends JSON directly.

    Returns the decoded dict or ``None`` if decoding fails.
    """
    if not header_value or not header_value.strip():
        return None

    # Try base64 first
    try:
        decoded_bytes = base64.b64decode(header_value, validate=True)
        return json.loads(decoded_bytes)
    except Exception:
        pass

    # Try raw JSON
    try:
        return json.loads(header_value)
    except Exception as e:
        logger.warning("Failed to decode X-Payment header: %s", e)
        return None
