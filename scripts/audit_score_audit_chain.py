#!/usr/bin/env python3
"""Generate a score-audit-chain verification snapshot artifact.

This AUD-3 follow-on makes the remaining legacy-tail truth explicitly auditable.
It fetches the full durable ``score_audit_chain`` surface, classifies each row
under the current verification policy, and writes a timestamped JSON report
under ``artifacts/``.

Typical production usage:
    railway run -s rhumb-api python3 scripts/audit_score_audit_chain.py

Local usage (with product env configured):
    python3 scripts/audit_score_audit_chain.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "packages" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routes._supabase import supabase_fetch  # noqa: E402
from services.score_audit_verification import (  # noqa: E402
    SCORE_AUDIT_VERIFICATION_SELECT_FIELDS,
    build_score_audit_verification_report,
)

SCHEMA_VERSION = "1.0.0"
REPORT_TYPE = "score_audit_chain_verification"
DEFAULT_REASON = "score_audit_chain_verification_snapshot"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts"
DEFAULT_PAGE_SIZE = 500


async def fetch_all_score_audit_rows(*, page_size: int = DEFAULT_PAGE_SIZE) -> list[dict[str, Any]]:
    """Fetch the full score_audit_chain surface in ascending time order."""
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        page = await supabase_fetch(
            f"score_audit_chain?select={SCORE_AUDIT_VERIFICATION_SELECT_FIELDS}"
            f"&order=created_at.asc&limit={page_size}&offset={offset}"
        )
        if not isinstance(page, list):
            raise RuntimeError("Failed to fetch score_audit_chain rows from Supabase.")

        parsed_page = [row for row in page if isinstance(row, dict)]
        if not parsed_page:
            return rows

        rows.extend(parsed_page)
        if len(parsed_page) < page_size:
            return rows
        offset += len(parsed_page)


async def generate_score_audit_verification_report() -> dict[str, Any]:
    rows = await fetch_all_score_audit_rows()
    return build_score_audit_verification_report(rows)


def build_report_bundle(
    report: dict[str, Any],
    *,
    operator: str,
    reason: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or datetime.now(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "generated_at": now.isoformat(),
        "provenance": {
            "system": "rhumb",
            "operator": operator,
            "reason": reason,
            "note": (
                "Full-table score_audit_chain verification snapshot under the current "
                "AUD-3 verification policy. Replay-verifiable rows, legacy key-version-only "
                "rows, and quarantined tails are all surfaced explicitly."
            ),
        },
        "report": report,
    }


def write_report_bundle(
    bundle: dict[str, Any],
    output_dir: Path,
    *,
    generated_at: datetime | None = None,
) -> Path:
    now = generated_at or datetime.fromisoformat(bundle["generated_at"])
    filename = f"score-audit-chain-verification-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(bundle, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a score_audit_chain verification snapshot artifact.",
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help="Reason tag for provenance (default: %(default)s)",
    )
    parser.add_argument(
        "--operator",
        default=os.environ.get("USER", "unknown"),
        help="Operator identity for provenance (default: env USER)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for the report artifact (default: artifacts/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report bundle to stdout without writing a file",
    )
    args = parser.parse_args(argv)

    generated_at = datetime.now(timezone.utc)
    report = asyncio.run(generate_score_audit_verification_report())
    bundle = build_report_bundle(
        report,
        operator=args.operator,
        reason=args.reason,
        generated_at=generated_at,
    )

    if args.dry_run:
        print(json.dumps(bundle, indent=2))
        return 0

    path = write_report_bundle(bundle, args.output_dir, generated_at=generated_at)
    print(f"Score-audit verification report written to: {path}")
    print(
        "Latest observed status: "
        f"{report.get('latest_observed', {}).get('verification_status', 'none')}"
    )
    print(f"Quarantined tail count: {report.get('quarantined_tail_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
