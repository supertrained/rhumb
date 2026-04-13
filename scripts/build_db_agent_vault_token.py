#!/usr/bin/env python3
"""Mint a short-lived signed DB agent_vault token for AUD-18 dogfood and ops.

Usage:
  python3 scripts/build_db_agent_vault_token.py \
    --connection-ref conn_reader \
    --dsn 'postgresql://user:pass@host:5432/db' \
    --agent-id agent_123 \
    --org-id org_456

The script reads the signing secret from RHUMB_DB_AGENT_VAULT_SECRET first,
then AUTH_JWT_SECRET / RHUMB_ADMIN_SECRET as fallbacks, matching the runtime
DB execute path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "packages" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.db_connection_registry import issue_agent_vault_dsn_token  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-ref", required=True, help="Bound connection_ref for the token")
    parser.add_argument("--dsn", required=True, help="PostgreSQL DSN to seal into the token")
    parser.add_argument("--agent-id", help="Optional agent_id binding")
    parser.add_argument("--org-id", help="Optional org_id binding")
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=300,
        help="Token lifetime in seconds (default: 300)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = issue_agent_vault_dsn_token(
        args.dsn,
        connection_ref=args.connection_ref,
        agent_id=args.agent_id,
        org_id=args.org_id,
        ttl_seconds=args.ttl_seconds,
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
