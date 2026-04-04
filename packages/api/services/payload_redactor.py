"""AUD-24: Payload redaction for audit/billing exports.

Prevents sensitive data from leaking through audit trail exports,
billing event queries, and trust surface APIs.

Sensitive patterns:
- API keys / tokens / secrets (Bearer tokens, API keys, passwords)
- Authorization headers
- Provider responses containing user PII or prompts
- Credential values from BYO/managed paths
- Raw request/response bodies

Design:
- Redaction runs on export/query output, NOT on storage
  (we want full detail for internal forensics, redacted for external access)
- Pattern-based + key-based detection
- Configurable redaction depth (strict vs permissive)
- Preserves structure — replaces values, not keys
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
import re
from pathlib import Path
from typing import Any
from uuid import UUID

# Keys that always get redacted (case-insensitive matching)
_SENSITIVE_KEYS = frozenset([
    "api_key", "apikey",
    "secret", "secret_key", "secretkey",
    "token", "access_token", "refresh_token", "bearer_token",
    "password", "passwd", "pwd",
    "authorization", "auth_header",
    "credential", "credentials",
    "private_key", "privatekey",
    "client_secret", "client_id",
    "x_api_key", "x_rhumb_key", "x_rhumb_admin_key",
    "cookie", "set_cookie",
    "session_id", "session_token",
    "jwt", "id_token",
])

# Value patterns that indicate secrets (even if the key isn't in the sensitive list)
_SECRET_VALUE_PATTERNS = [
    re.compile(r"^(?:Bearer|Basic|Token)\s+\S+", re.IGNORECASE),  # Auth headers
    re.compile(r"^rhumb_[a-f0-9]{32,}$"),  # Rhumb API keys
    re.compile(r"^sk[-_](?:live|test)[-_]\S+$"),  # Stripe-style keys
    re.compile(r"^xoxb-\S+$"),  # Slack bot tokens
    re.compile(r"^ghp_\S+$"),  # GitHub PATs
    re.compile(r"^(?:AIza|ya29\.)\S+$"),  # Google API/OAuth tokens
    re.compile(r"^eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\."),  # JWTs
    re.compile(r"^(?:tvly|exa|unst)[-_][A-Za-z0-9]{7,}$", re.IGNORECASE),  # Known provider keys
    re.compile(r"^BSA[A-Za-z0-9]{16,}$"),  # Brave Search API keys
    re.compile(r"^[A-Za-z]{2,8}[-_][A-Za-z0-9]{20,}$"),  # Provider-style prefix-long secrets
    re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$"),  # Long base64 (likely keys)
]

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
UNSERIALIZABLE = "[UNSERIALIZABLE]"


def _redact_string(value: str, *, strict: bool) -> str:
    if not strict:
        return value
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.match(value):
            return REDACTED
    return value


def _truncate_string(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}…{TRUNCATED}"


def sanitize_external_payload(
    data: Any,
    *,
    depth: int = 0,
    max_depth: int = 6,
    max_items: int = 50,
    max_string_length: int = 256,
    strict: bool = True,
) -> Any:
    """Convert arbitrary data into a bounded, JSON-safe, redacted structure.

    This is the default-safe serializer for external/API-facing payloads where we
    want to preserve enough structure for debugging and analytics without
    allowing raw secrets, pathological nesting, giant strings, or unserializable
    Python objects to leak through.
    """
    if depth > max_depth:
        return TRUNCATED

    if isinstance(data, dict):
        items = list(data.items())
        result: dict[str, Any] = {}
        for key, value in items[:max_items]:
            safe_key = _truncate_string(str(key), max_length=max_string_length)
            normalized_key = str(key).lower().replace("-", "_").replace(" ", "_")
            if strict and normalized_key in _SENSITIVE_KEYS:
                result[safe_key] = REDACTED
                continue
            result[safe_key] = sanitize_external_payload(
                value,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                strict=strict,
            )
        if len(items) > max_items:
            result["__truncated_items__"] = len(items) - max_items
        return result

    if isinstance(data, (list, tuple, set, frozenset)):
        items = list(data)
        result = [
            sanitize_external_payload(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                strict=strict,
            )
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            result.append(TRUNCATED)
        return result

    if isinstance(data, str):
        return _truncate_string(_redact_string(data, strict=strict), max_length=max_string_length)

    if isinstance(data, (bytes, bytearray, memoryview)):
        return TRUNCATED

    if isinstance(data, (datetime, date, time)):
        return data.isoformat()

    if isinstance(data, (UUID, Path, Decimal)):
        return str(data)

    if isinstance(data, Enum):
        return sanitize_external_payload(
            data.value,
            depth=depth + 1,
            max_depth=max_depth,
            max_items=max_items,
            max_string_length=max_string_length,
            strict=strict,
        )

    if data is None or isinstance(data, (bool, int, float)):
        return data

    return f"{UNSERIALIZABLE}:{type(data).__name__}"


def redact_payload(
    data: Any,
    *,
    depth: int = 0,
    max_depth: int = 20,
    strict: bool = True,
) -> Any:
    """Recursively redact sensitive values from a data structure.

    Args:
        data: The data to redact (dict, list, or scalar)
        depth: Current recursion depth
        max_depth: Maximum recursion depth
        strict: If True, also redact values matching secret patterns
                If False, only redact by key name

    Returns:
        A deep copy with sensitive values replaced by [REDACTED]
    """
    if depth > max_depth:
        return REDACTED  # Over-deep structures get fully redacted

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = str(key).lower().replace("-", "_").replace(" ", "_")
            if key_lower in _SENSITIVE_KEYS:
                result[key] = REDACTED
            else:
                redacted_value = redact_payload(
                    value, depth=depth + 1, max_depth=max_depth, strict=strict
                )
                result[key] = redacted_value
        return result

    elif isinstance(data, (list, tuple)):
        return [
            redact_payload(item, depth=depth + 1, max_depth=max_depth, strict=strict)
            for item in data
        ]

    elif isinstance(data, str):
        return _redact_string(data, strict=strict)

    else:
        return data


def redact_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Redact sensitive HTTP headers."""
    if headers is None:
        return None
    result = {}
    for key, value in headers.items():
        key_lower = key.lower().replace("-", "_")
        if key_lower in _SENSITIVE_KEYS or key_lower.startswith("x_rhumb"):
            result[key] = REDACTED
        elif key_lower == "authorization":
            result[key] = REDACTED
        elif isinstance(value, str) and _redact_string(value, strict=True) == REDACTED:
            result[key] = REDACTED
        else:
            result[key] = value
    return result


def redact_event_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Redact an audit or billing event detail field for export."""
    if detail is None:
        return {}
    return sanitize_external_payload(redact_payload(detail, strict=True), strict=False)


def redact_event_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Redact an audit or billing event metadata field for export."""
    if metadata is None:
        return {}
    return sanitize_external_payload(redact_payload(metadata, strict=True), strict=False)
