#!/usr/bin/env python3
"""Publish a chain-anchor bundle as an external witness artifact.

Creates fresh checkpoints for score_audit_chain, audit_events, and/or
billing_events via the Rhumb admin API, then writes a deterministic JSON anchor bundle under
``anchors/`` suitable for committing to Git as a public witness.

This is the first external-anchor publication path for AUD-3.  It is honest
about what it provides: a timestamped, hash-pinned snapshot of chain heads
committed to a public repo -- not a blockchain or Merkle-tree anchor (yet).

Usage (production via Railway):
    railway run -s rhumb-api python3 scripts/publish_chain_anchor.py

Usage (local dev with API running on localhost):
    RHUMB_API_URL=http://localhost:8000 \\
    RHUMB_ADMIN_KEY=test-secret \\
    python3 scripts/publish_chain_anchor.py

Production-friendly env fallbacks:
- API base: `RHUMB_API_URL` → `AUTH_API_URL` → `https://api.rhumb.dev`
- Admin secret: `RHUMB_ADMIN_KEY` → `RHUMB_ADMIN_SECRET`

Options:
    --streams score_audit_chain,audit_events,billing_events
                                           Comma-separated streams (default: all three)
    --reason  <string>                      Checkpoint reason tag (default: external_anchor)
    --operator <string>                     Who initiated this publication
    --output-dir <path>                     Override output directory (default: anchors/)
    --dry-run                               Print bundle to stdout, don't write file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SCHEMA_VERSION = "1.0.0"
BUNDLE_TYPE = "chain_anchor"
DEFAULT_STREAMS = ["score_audit_chain", "audit_events", "billing_events"]
DEFAULT_REASON = "external_anchor"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "anchors"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _api_base() -> str:
    return (
        os.environ.get("RHUMB_API_URL")
        or os.environ.get("AUTH_API_URL")
        or "https://api.rhumb.dev"
    ).rstrip("/")


def _admin_key() -> str:
    return os.environ.get("RHUMB_ADMIN_KEY") or _require_env("RHUMB_ADMIN_SECRET")


def create_checkpoint(
    stream_name: str,
    reason: str,
    metadata: dict[str, Any],
    *,
    api_base: str | None = None,
    admin_key: str | None = None,
) -> dict[str, Any]:
    """Call the admin checkpoint endpoint for a single stream.

    Returns the full JSON response body.
    """
    base = api_base or _api_base()
    key = admin_key or _admin_key()
    url = f"{base}/v1/admin/trust/chain-checkpoints/{stream_name}"

    body = json.dumps({
        "reason": reason,
        "metadata": metadata,
        "flush": True,
    }).encode("utf-8")

    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Rhumb-Admin-Key": key,
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(
            f"Checkpoint request failed for {stream_name}: "
            f"HTTP {exc.code} — {error_body}"
        ) from exc


def compute_bundle_hash(streams: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the streams object.

    This is a public, non-keyed hash so anyone with the bundle can verify
    it hasn't been tampered with post-publication.  The individual
    checkpoint_hash fields inside each stream entry are HMAC-signed and
    require the signing key to verify.
    """
    canonical = json.dumps(streams, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_anchor_bundle(
    checkpoints: dict[str, dict[str, Any]],
    *,
    operator: str,
    reason: str,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the anchor bundle from collected checkpoint responses."""
    now = published_at or datetime.now(timezone.utc)

    streams: dict[str, Any] = {}
    for stream_name, response in checkpoints.items():
        if response.get("status") == "skipped":
            streams[stream_name] = {
                "status": "skipped",
                "detail": response.get("detail", "Stream empty"),
            }
        elif response.get("status") == "created":
            cp = response["checkpoint"]
            metadata = cp.get("metadata", {}) or {}
            verification_status = metadata.get("verification_status")
            stream_status = (
                "anchored_with_quarantined_tail"
                if verification_status == "latest_verified_head_with_quarantined_tail"
                else "anchored"
            )
            stream_payload = {
                "status": stream_status,
                "checkpoint_id": cp["checkpoint_id"],
                "source_head_hash": cp["source_head_hash"],
                "source_head_sequence": cp["source_head_sequence"],
                "source_key_version": cp.get("source_key_version"),
                "checkpoint_hash": cp["checkpoint_hash"],
                "key_version": cp["key_version"],
                "created_at": cp["created_at"],
                "metadata": metadata,
            }
            if verification_status:
                stream_payload["verification_status"] = verification_status
            if metadata.get("quarantined_tail_count") is not None:
                stream_payload["quarantined_tail_count"] = metadata.get("quarantined_tail_count")
            if metadata.get("verified_head_entry_id"):
                stream_payload["verified_head_entry_id"] = metadata.get("verified_head_entry_id")
            if metadata.get("latest_observed_entry_id"):
                stream_payload["latest_observed_entry_id"] = metadata.get("latest_observed_entry_id")
            streams[stream_name] = stream_payload

    bundle_hash = compute_bundle_hash(streams)

    return {
        "schema_version": SCHEMA_VERSION,
        "bundle_type": BUNDLE_TYPE,
        "published_at": now.isoformat(),
        "provenance": {
            "system": "rhumb",
            "operator": operator,
            "reason": reason,
            "note": (
                "First external anchor witness -- HMAC-signed checkpoint bundle "
                "committed to Git for public verifiability. Individual checkpoint_hash "
                "values are HMAC-SHA256 (require signing key to verify). The bundle_hash "
                "is plain SHA-256 of the canonical streams payload (publicly verifiable)."
            ),
        },
        "streams": streams,
        "bundle_hash": bundle_hash,
    }


def write_anchor_bundle(
    bundle: dict[str, Any],
    output_dir: Path,
    *,
    published_at: datetime | None = None,
) -> Path:
    """Write the anchor bundle to a timestamped JSON file.

    Returns the path of the written file.
    """
    now = published_at or datetime.fromisoformat(bundle["published_at"])
    filename = f"chain-anchor-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(
        json.dumps(bundle, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish a chain-anchor bundle as an external witness artifact.",
    )
    parser.add_argument(
        "--streams",
        default=",".join(DEFAULT_STREAMS),
        help="Comma-separated stream names to checkpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help="Checkpoint reason tag (default: %(default)s)",
    )
    parser.add_argument(
        "--operator",
        default=os.environ.get("USER", "unknown"),
        help="Operator identity for provenance (default: $USER)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for anchor bundle (default: anchors/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print bundle to stdout without writing a file",
    )
    args = parser.parse_args(argv)

    streams = [s.strip() for s in args.streams.split(",") if s.strip()]
    if not streams:
        print("Error: no streams specified", file=sys.stderr)
        return 1

    published_at = datetime.now(timezone.utc)
    metadata = {"operator": args.operator, "publication_reason": args.reason}

    # Collect checkpoints from each stream
    checkpoints: dict[str, dict[str, Any]] = {}
    for stream_name in streams:
        print(f"  Checkpointing {stream_name}...", file=sys.stderr)
        try:
            response = create_checkpoint(stream_name, args.reason, metadata)
            checkpoints[stream_name] = response
            status = response.get("status", "unknown")
            print(f"    -> {status}", file=sys.stderr)
        except RuntimeError as exc:
            print(f"    -> FAILED: {exc}", file=sys.stderr)
            return 1

    # Build the anchor bundle
    bundle = build_anchor_bundle(
        checkpoints,
        operator=args.operator,
        reason=args.reason,
        published_at=published_at,
    )

    if args.dry_run:
        print(json.dumps(bundle, indent=2))
        return 0

    # Write to disk
    path = write_anchor_bundle(bundle, args.output_dir, published_at=published_at)
    print(f"\n  Anchor bundle written to: {path}", file=sys.stderr)
    print(f"  Bundle hash: {bundle['bundle_hash']}", file=sys.stderr)

    anchored = [s for s, v in bundle["streams"].items() if v.get("status") == "anchored"]
    skipped = [s for s, v in bundle["streams"].items() if v.get("status") == "skipped"]
    if anchored:
        print(f"  Anchored streams: {', '.join(anchored)}", file=sys.stderr)
    if skipped:
        print(f"  Skipped streams (empty): {', '.join(skipped)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
