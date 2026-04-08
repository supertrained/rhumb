"""Connection-ref registry, DB agent_vault token helpers, and provider detection.

Wave 1 intentionally supports only *read-first* database access, but it does
support two credential modes for resolving the underlying PostgreSQL DSN:

1) ``byok``
   The DSN is resolved from an environment variable using a deterministic
   naming convention:

       connection_ref="conn_reader"  →  env RHUMB_DB_CONN_READER

   This keeps secrets out of Supabase rows and lets operators rotate DSNs
   without code changes.

2) ``agent_vault``
   Hosted Rhumb currently supports two DB agent_vault input shapes:
   - compatibility fallback: raw PostgreSQL DSN in ``X-Agent-Token``
   - stronger bridge: short-lived signed DB vault token in ``X-Agent-Token``

   Rhumb must treat either form as transient secret material and never log or
   persist the DSN itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

_CONN_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_AGENT_VAULT_DSN_MAX_CHARS = 4096
_ALLOWED_DSN_SCHEMES = {"postgresql", "postgres"}
_SUPABASE_HOST_SUFFIXES = (".supabase.co", ".supabase.com")
_DB_AGENT_VAULT_TOKEN_PREFIX = "rhdbv1."
_DB_AGENT_VAULT_SECRET_ENV_KEYS = (
    "RHUMB_DB_AGENT_VAULT_SECRET",
    "AUTH_JWT_SECRET",
    "RHUMB_ADMIN_SECRET",
)


class ConnectionRefError(ValueError):
    """Raised when a connection_ref cannot be resolved."""


class AgentVaultDsnError(ValueError):
    """Raised when an agent_vault DSN cannot be validated."""


@dataclass(frozen=True, slots=True)
class IssuedDbAgentVaultToken:
    token: str
    expires_at: int


def validate_connection_ref(connection_ref: str) -> None:
    """Validate a connection_ref.

    Raises ConnectionRefError if the ref is malformed.
    """
    if not _CONN_REF_RE.fullmatch(connection_ref):
        raise ConnectionRefError(
            f"Invalid connection_ref '{connection_ref}': "
            "must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def issue_db_agent_vault_token(
    dsn: str,
    *,
    connection_ref: str,
    agent_id: str | None = None,
    org_id: str | None = None,
    ttl_seconds: int = 300,
    issued_at: int | None = None,
    secret: str | bytes | None = None,
) -> IssuedDbAgentVaultToken:
    """Issue a short-lived signed DB agent_vault token for a PostgreSQL DSN.

    This is a bounded bridge hardening step for hosted DB reads. It lets a
    trusted caller replace a raw DSN-in-header handoff with a signed token that
    binds the DSN to a specific connection_ref and expiry.
    """
    validate_connection_ref(connection_ref)
    normalized_dsn = _validate_postgres_dsn(
        dsn,
        error_message="DB vault token payload must contain a postgresql:// DSN",
    )

    # Keep expiry anchored to actual issue time even if a caller passes an
    # older compatibility timestamp for deterministic test fixtures.
    now = int(time.time())
    expiry = now + max(int(ttl_seconds), 1)
    payload = {
        "connection_ref": connection_ref,
        "dsn": normalized_dsn,
        "exp": expiry,
    }
    if agent_id:
        payload["agent_id"] = agent_id
    if org_id:
        payload["org_id"] = org_id
    payload_bytes = _canonicalize_token_payload(payload)
    signature = hmac.new(
        _get_db_agent_vault_secret(secret),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    token = f"{_DB_AGENT_VAULT_TOKEN_PREFIX}{_b64url_encode(payload_bytes)}.{signature}"
    return IssuedDbAgentVaultToken(token=token, expires_at=expiry)


def issue_agent_vault_dsn_token(
    dsn: str,
    *,
    connection_ref: str,
    agent_id: str | None = None,
    org_id: str | None = None,
    ttl_seconds: int = 300,
    issued_at: int | None = None,
    secret: str | bytes | None = None,
) -> str:
    """Backwards-compatible helper that returns only the signed token string."""
    return issue_db_agent_vault_token(
        dsn,
        connection_ref=connection_ref,
        agent_id=agent_id,
        org_id=org_id,
        ttl_seconds=ttl_seconds,
        issued_at=issued_at,
        secret=secret,
    ).token


def resolve_agent_vault_dsn(
    agent_token: str | None,
    *,
    connection_ref: str | None = None,
    expected_connection_ref: str | None = None,
    expected_agent_id: str | None = None,
    expected_org_id: str | None = None,
    now: int | None = None,
    secret: str | bytes | None = None,
) -> str:
    """Resolve and validate an agent-provided DB credential.

    Accepted forms:
    - raw PostgreSQL DSN (compatibility fallback)
    - signed short-lived ``rhdbv1.`` DB vault token

    The returned DSN is still treated as transient secret material and must
    never be logged or persisted.

    Raises AgentVaultDsnError when the token is missing or invalid.
    """
    if agent_token is None or not agent_token.strip():
        raise AgentVaultDsnError(
            "X-Agent-Token header required for agent_vault credential mode"
        )

    token = agent_token.strip()
    if len(token) > _AGENT_VAULT_DSN_MAX_CHARS:
        raise AgentVaultDsnError("X-Agent-Token value too long")

    if token.startswith(_DB_AGENT_VAULT_TOKEN_PREFIX):
        payload = _decode_signed_db_agent_vault_token(
            token,
            connection_ref=connection_ref or expected_connection_ref,
            expected_agent_id=expected_agent_id,
            expected_org_id=expected_org_id,
            now=now,
            secret=secret,
        )
        dsn = payload.get("dsn")
        if not isinstance(dsn, str):
            raise AgentVaultDsnError("Signed DB agent_vault token is missing a DSN")
        return _validate_postgres_dsn(
            dsn,
            error_message="Signed DB agent_vault token must contain a postgresql:// DSN",
        )

    return _validate_postgres_dsn(
        token,
        error_message="X-Agent-Token must be a postgresql:// DSN or signed rhdbv1 token",
    )


def resolve_dsn(connection_ref: str) -> str:
    """Resolve a connection_ref to a PostgreSQL DSN.

    Raises ConnectionRefError if the ref is malformed, unset, or configured
    to a non-PostgreSQL placeholder value.
    """
    validate_connection_ref(connection_ref)

    env_key = f"RHUMB_DB_{connection_ref.upper()}"
    dsn = os.environ.get(env_key)
    if not dsn:
        raise ConnectionRefError(
            f"No DSN configured for connection_ref '{connection_ref}' "
            f"(expected env var {env_key})"
        )

    dsn = dsn.strip()
    parsed = urlparse(dsn)
    if parsed.scheme not in _ALLOWED_DSN_SCHEMES:
        raise ConnectionRefError(
            f"connection_ref '{connection_ref}' is configured via env '{env_key}' "
            "but is disabled or invalid"
        )

    return dsn


def detect_postgres_provider(dsn: str) -> str:
    """Return provider attribution for a PostgreSQL-compatible DSN.

    Supabase-backed Postgres uses distinct hostnames, for example
    ``db.<project-ref>.supabase.co`` or ``*.pooler.supabase.com``.
    If the hostname does not clearly indicate Supabase, default to the
    generic ``postgresql`` attribution.
    """
    hostname = (urlparse(dsn).hostname or "").lower()
    if hostname.endswith(_SUPABASE_HOST_SUFFIXES):
        return "supabase"
    return "postgresql"


def _validate_postgres_dsn(dsn: str, *, error_message: str) -> str:
    normalized = dsn.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in _ALLOWED_DSN_SCHEMES:
        raise AgentVaultDsnError(error_message)
    return normalized


def _decode_signed_db_agent_vault_token(
    token: str,
    *,
    connection_ref: str | None,
    expected_agent_id: str | None,
    expected_org_id: str | None,
    now: int | None,
    secret: str | bytes | None,
) -> dict[str, object]:
    token_body = token[len(_DB_AGENT_VAULT_TOKEN_PREFIX):]
    payload_b64, separator, signature = token_body.partition(".")
    if not separator or not payload_b64 or not signature:
        raise AgentVaultDsnError("Signed DB agent_vault token is malformed")

    try:
        payload_bytes = _b64url_decode(payload_b64)
    except Exception as exc:
        raise AgentVaultDsnError("Signed DB agent_vault token payload is invalid") from exc

    expected_signature = hmac.new(
        _get_db_agent_vault_secret(secret),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise AgentVaultDsnError("Signed DB agent_vault token signature is invalid")

    try:
        payload = json.loads(payload_bytes)
    except Exception as exc:
        raise AgentVaultDsnError("Signed DB agent_vault token payload is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise AgentVaultDsnError("Signed DB agent_vault token payload must be an object")

    payload_connection_ref = payload.get("connection_ref")
    if not isinstance(payload_connection_ref, str):
        raise AgentVaultDsnError("Signed DB agent_vault token is missing connection_ref")
    validate_connection_ref(payload_connection_ref)

    expiry = payload.get("exp")
    if not isinstance(expiry, int):
        raise AgentVaultDsnError("Signed DB agent_vault token is missing expiry")
    current_time = int(time.time()) if now is None else int(now)
    if expiry < current_time:
        raise AgentVaultDsnError("Signed DB agent_vault token has expired")

    if connection_ref is not None:
        validate_connection_ref(connection_ref)
        if payload_connection_ref != connection_ref:
            raise AgentVaultDsnError(
                "Signed DB agent_vault token connection_ref does not match the request"
            )

    if expected_agent_id is not None:
        payload_agent_id = payload.get("agent_id")
        if payload_agent_id is not None and payload_agent_id != expected_agent_id:
            raise AgentVaultDsnError(
                "Signed DB agent_vault token agent_id does not match the request"
            )

    if expected_org_id is not None:
        payload_org_id = payload.get("org_id")
        if payload_org_id is not None and payload_org_id != expected_org_id:
            raise AgentVaultDsnError(
                "Signed DB agent_vault token org_id does not match the request"
            )

    return payload


def _get_db_agent_vault_secret(secret: str | bytes | None) -> bytes:
    if secret is not None:
        return secret if isinstance(secret, bytes) else secret.encode("utf-8")

    for env_key in _DB_AGENT_VAULT_SECRET_ENV_KEYS:
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value.encode("utf-8")

    raise AgentVaultDsnError(
        "Signed DB agent_vault tokens are not configured on this host"
    )


def _canonicalize_token_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
