"""Connection-ref registry — maps agent connection references to DSNs.

Wave 1 intentionally supports only *read-first* database access, but it does
support two credential modes for resolving the underlying PostgreSQL DSN:

1) ``byok``
   The DSN is resolved from an environment variable using a deterministic
   naming convention:

       connection_ref="conn_reader"  →  env RHUMB_DB_CONN_READER

   This keeps secrets out of Supabase rows and lets operators rotate DSNs
   without code changes.

2) ``agent_vault``
   The DSN is provided per-request by the agent (typically via the
   ``X-Agent-Token`` header on execute). Rhumb must treat this DSN as a
   transient secret and never persist or echo it.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

_CONN_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_AGENT_VAULT_DSN_MAX_CHARS = 4096
_ALLOWED_DSN_SCHEMES = {"postgresql", "postgres"}


class ConnectionRefError(ValueError):
    """Raised when a connection_ref cannot be resolved."""


class AgentVaultDsnError(ValueError):
    """Raised when an agent_vault DSN cannot be validated."""


def validate_connection_ref(connection_ref: str) -> None:
    """Validate a connection_ref.

    Raises ConnectionRefError if the ref is malformed.
    """
    if not _CONN_REF_RE.fullmatch(connection_ref):
        raise ConnectionRefError(
            f"Invalid connection_ref '{connection_ref}': "
            "must be lowercase alphanumeric with underscores, 1-64 chars"
        )


def resolve_agent_vault_dsn(agent_token: str | None) -> str:
    """Resolve and validate an agent-provided DSN.

    The DSN is treated as a transient secret (for example supplied via the
    ``X-Agent-Token`` header). This function must never log or persist the
    value; it only validates shape and returns it.

    Raises AgentVaultDsnError when the DSN is missing or invalid.
    """
    if agent_token is None or not agent_token.strip():
        raise AgentVaultDsnError(
            "X-Agent-Token header required for agent_vault credential mode"
        )

    dsn = agent_token.strip()
    if len(dsn) > _AGENT_VAULT_DSN_MAX_CHARS:
        raise AgentVaultDsnError("X-Agent-Token value too long")

    parsed = urlparse(dsn)
    if parsed.scheme not in _ALLOWED_DSN_SCHEMES:
        raise AgentVaultDsnError("X-Agent-Token must be a postgresql:// DSN")

    return dsn


def resolve_dsn(connection_ref: str) -> str:
    """Resolve a connection_ref to a PostgreSQL DSN.

    Raises ConnectionRefError if the ref is malformed or unset.
    """
    validate_connection_ref(connection_ref)

    env_key = f"RHUMB_DB_{connection_ref.upper()}"
    dsn = os.environ.get(env_key)
    if not dsn:
        raise ConnectionRefError(
            f"No DSN configured for connection_ref '{connection_ref}' "
            f"(expected env var {env_key})"
        )
    return dsn
