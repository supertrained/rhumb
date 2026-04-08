"""Connection-ref registry — maps agent connection references to DSNs.

Wave 1 is deliberately simple: BYOK connection_ref values are looked up from
environment variables using a deterministic naming convention:

    connection_ref="conn_reader"  →  env RHUMB_DB_CONN_READER

This keeps secrets out of Supabase rows and lets operators rotate DSNs
without code changes. A future wave can add a real agent_vault bridge.
"""

from __future__ import annotations

import os
import re

_CONN_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ConnectionRefError(ValueError):
    """Raised when a connection_ref cannot be resolved."""


def resolve_dsn(connection_ref: str) -> str:
    """Resolve a connection_ref to a PostgreSQL DSN.

    Raises ConnectionRefError if the ref is malformed or unset.
    """
    if not _CONN_REF_RE.fullmatch(connection_ref):
        raise ConnectionRefError(
            f"Invalid connection_ref '{connection_ref}': "
            "must be lowercase alphanumeric with underscores, 1-64 chars"
        )

    env_key = f"RHUMB_DB_{connection_ref.upper()}"
    dsn = os.environ.get(env_key)
    if not dsn:
        raise ConnectionRefError(
            f"No DSN configured for connection_ref '{connection_ref}' "
            f"(expected env var {env_key})"
        )
    return dsn
