#!/usr/bin/env python3
"""Read-only inspector for Awal / Coinbase Payments MCP local wallet state.

Purpose:
- Recover evidence of locally known wallet identities without mutating state
- Help unblock x402 live reruns when the Awal Electron daemon is wedged
- Avoid destructive resets until we know whether the funded wallet still exists on disk

By default the script scans the Electron IndexedDB/LevelDB directory used by
`https://payments-mcp.coinbase.com` and extracts candidate wallet addresses,
email addresses, and a lightweight process snapshot.

Usage:
  python3 rhumb/scripts/inspect_awal_wallet_state.py
  python3 rhumb/scripts/inspect_awal_wallet_state.py --json
  AWAL_LEVELDB_DIR=/path/to/leveldb python3 rhumb/scripts/inspect_awal_wallet_state.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_LEVELDB_DIR = (
    Path.home()
    / "Library/Application Support/Electron/IndexedDB/https_payments-mcp.coinbase.com_0.indexeddb.leveldb"
)

ADDRESS_RE = re.compile(rb"0x[a-fA-F0-9]{40}")
EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _safe_decode(blob: bytes) -> str:
    return blob.decode("utf-8", errors="ignore")


def _scan_leveldb(leveldb_dir: Path) -> dict[str, Any]:
    addresses: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "files": set(), "contexts": []})
    emails: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "files": set()})
    inspected_files: list[str] = []

    if not leveldb_dir.exists():
        return {
            "exists": False,
            "path": str(leveldb_dir),
            "inspected_files": [],
            "addresses": [],
            "emails": [],
        }

    for file_path in sorted(leveldb_dir.iterdir()):
        if not file_path.is_file():
            continue
        inspected_files.append(file_path.name)
        try:
            raw = file_path.read_bytes()
        except OSError:
            continue

        for match in ADDRESS_RE.finditer(raw):
            address = match.group(0).decode("ascii", errors="ignore")
            entry = addresses[address]
            entry["count"] += 1
            entry["files"].add(file_path.name)
            start = max(0, match.start() - 24)
            end = min(len(raw), match.end() + 40)
            snippet = _safe_decode(raw[start:end]).replace("\n", " ").strip()
            if snippet and snippet not in entry["contexts"] and len(entry["contexts"]) < 3:
                entry["contexts"].append(snippet)

        for match in EMAIL_RE.finditer(raw):
            email = match.group(0).decode("ascii", errors="ignore")
            entry = emails[email]
            entry["count"] += 1
            entry["files"].add(file_path.name)

    return {
        "exists": True,
        "path": str(leveldb_dir),
        "inspected_files": inspected_files,
        "addresses": [
            {
                "address": address,
                "count": meta["count"],
                "files": sorted(meta["files"]),
                "contexts": meta["contexts"],
            }
            for address, meta in sorted(addresses.items(), key=lambda item: (-item[1]["count"], item[0].lower()))
        ],
        "emails": [
            {
                "email": email,
                "count": meta["count"],
                "files": sorted(meta["files"]),
            }
            for email, meta in sorted(emails.items(), key=lambda item: (-item[1]["count"], item[0].lower()))
        ],
    }


def _process_snapshot() -> list[dict[str, str]]:
    try:
        proc = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:  # pragma: no cover - best effort only
        return [{"error": f"ps failed: {exc}"}]

    rows: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        lowered = line.lower()
        if "payments-mcp-server" in lowered or "awal" in lowered:
            rows.append({"line": line})
    return rows


def _build_summary(scan: dict[str, Any], processes: list[dict[str, str]]) -> str:
    if not scan.get("exists"):
        return "Awal Electron LevelDB store not found. No on-disk recovery evidence available from the default path."

    addresses = scan.get("addresses", [])
    if not addresses:
        return "Awal Electron LevelDB store exists, but no wallet addresses were recovered from the scanned files."

    if len(addresses) == 1:
        return (
            "Recovered one wallet identity from the local Awal Electron store. "
            "Safest next step is re-auth/account selection against that identity before any reset."
        )

    return (
        f"Recovered {len(addresses)} wallet identities from the local Awal Electron store. "
        "That means the prior wallet state still exists on disk; prefer account-selection or controlled restart "
        "over wiping app data."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local Awal / Coinbase Payments MCP wallet state (read-only)")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--leveldb-dir",
        default=os.environ.get("AWAL_LEVELDB_DIR", str(DEFAULT_LEVELDB_DIR)),
        help="Override the LevelDB directory to inspect",
    )
    args = parser.parse_args()

    leveldb_dir = Path(args.leveldb_dir).expanduser()
    scan = _scan_leveldb(leveldb_dir)
    processes = _process_snapshot()
    payload = {
        "leveldb": scan,
        "processes": processes,
        "summary": _build_summary(scan, processes),
        "read_only": True,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Awal wallet state inspection (read-only)")
    print(f"LevelDB path: {scan['path']}")
    print(f"Store exists: {'yes' if scan.get('exists') else 'no'}")
    if scan.get("exists"):
        print(f"Inspected files: {', '.join(scan.get('inspected_files', [])) or '(none)'}")
        print("\nRecovered wallet addresses:")
        if scan.get("addresses"):
            for item in scan["addresses"]:
                print(f"- {item['address']}  (matches={item['count']}, files={', '.join(item['files'])})")
                for context in item.get("contexts", []):
                    print(f"    context: {context}")
        else:
            print("- none")

        print("\nRecovered emails:")
        if scan.get("emails"):
            for item in scan["emails"]:
                print(f"- {item['email']}  (matches={item['count']}, files={', '.join(item['files'])})")
        else:
            print("- none")

    print("\nRelevant processes:")
    if processes:
        for row in processes:
            print(f"- {row.get('line', row.get('error', 'unknown'))}")
    else:
        print("- none")

    print(f"\nSummary: {payload['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
