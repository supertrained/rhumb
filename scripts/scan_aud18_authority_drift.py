#!/usr/bin/env python3
"""Scan tracked Rhumb authority surfaces for stale AUD-18 wording drift.

Purpose:
- keep provider-controlled wording from collapsing back to BYOK-only or other
  stale public shorthand
- keep execution-rail wording from drifting back to older auth/payment framing
- avoid expensive broad recursive greps by scanning only tracked high-signal
  authority surfaces

Exit codes:
- 0: no drift matches found
- 1: one or more drift matches found
- 2: usage / repo discovery error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]

DEFAULT_SCAN_PATHS = (
    Path("README.md"),
    Path("docs/API.md"),
    Path("examples"),
    Path("llms.txt"),
    Path("agent-capabilities.json"),
    Path("packages/shared/pricing.json"),
    Path("packages/api/pricing.json"),
    Path("packages/astro-web/src"),
    Path("packages/astro-web/public"),
    Path("packages/web/app"),
    Path("packages/web/public"),
    Path("packages/mcp/README.md"),
    Path("packages/mcp/package.json"),
    Path("packages/mcp/server.json"),
    Path("scripts/generate_agent_capabilities.py"),
)

SKIP_PARTS = {
    ".git",
    ".next",
    ".vercel",
    "dist",
    "coverage",
    "node_modules",
    "artifacts",
    "tests",
    "__snapshots__",
}

TEXT_SUFFIXES = {
    ".astro",
    ".cjs",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mdx",
    ".mjs",
    ".py",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class DriftPattern:
    key: str
    note: str
    regex: re.Pattern[str]


DRIFT_PATTERNS: tuple[DriftPattern, ...] = (
    DriftPattern(
        key="byok-only",
        note="provider-controlled path collapsed to BYOK-only",
        regex=re.compile(r"\bBYOK-only\b", re.IGNORECASE),
    ),
    DriftPattern(
        key="own-credentials-shorthand",
        note="generic \"your own credentials\" wording can obscure BYOK or Agent Vault",
        regex=re.compile(r"your own (?:provider )?credentials", re.IGNORECASE),
    ),
    DriftPattern(
        key="legacy-wallet-prefund-name",
        note="older wallet-prefunded API-key phrasing",
        regex=re.compile(r"wallet-prefunded API key", re.IGNORECASE),
    ),
    DriftPattern(
        key="legacy-wallet-prefund-balance-name",
        note="older wallet-prefunded balance phrasing",
        regex=re.compile(r"wallet-prefunded balance", re.IGNORECASE),
    ),
    DriftPattern(
        key="legacy-api-key-or-x402",
        note="older auth/payment framing that predates the live rail story",
        regex=re.compile(r"api key or x402 payment", re.IGNORECASE),
    ),
    DriftPattern(
        key="legacy-machine-auth-tag",
        note="older machine-readable auth tag that predates rail-based wording",
        regex=re.compile(r"api_key_or_x402", re.IGNORECASE),
    ),
    DriftPattern(
        key="managed-mode-shorthand",
        note="older managed-mode shorthand on public authority surfaces",
        regex=re.compile(r"\bmanaged mode\b", re.IGNORECASE),
    ),
    DriftPattern(
        key="mode-number-framing",
        note="older numbered Mode framing on public authority surfaces",
        regex=re.compile(r"\bMode\s+[1-4]\b", re.IGNORECASE),
    ),
    DriftPattern(
        key="credential-mode-mental-model-shorthand",
        note="older credential-mode shorthand on authority surfaces that should now say credential path",
        regex=re.compile(r"the change is the credential mode, not the product mental model", re.IGNORECASE),
    ),
    DriftPattern(
        key="rhumb-managed-label-casing",
        note="older governed-path label casing that should now stay `Rhumb-managed`",
        regex=re.compile(r"\bRhumb-Managed\b"),
    ),
    DriftPattern(
        key="managed-checklist-shorthand",
        note="older checklist shorthand that should now name the governed path as `Rhumb-managed`",
        regex=re.compile(r"Prefer managed, Agent Vault, or x402 over raw BYOK", re.IGNORECASE),
    ),
    DriftPattern(
        key="legacy-managed-anchor",
        note="older glossary anchor still leaks `managed-mode` instead of `rhumb-managed`",
        regex=re.compile(r"#managed-mode\b|\bid:\s*[\"']managed-mode[\"']"),
    ),
    DriftPattern(
        key="existing-stack-third-path-shorthand",
        note="homepage wording that makes existing stack sound like a third path instead of BYOK or Agent Vault",
        regex=re.compile(r"Use BYOK, Agent Vault, or your existing stack", re.IGNORECASE),
    ),
    DriftPattern(
        key="ambiguous-byok-api-key-shorthand",
        note="BYOK wording that can blur provider API keys with the governed Rhumb API key",
        regex=re.compile(r"Bring your own API key|Pass your own API keys? at execution time", re.IGNORECASE),
    ),
    DriftPattern(
        key="ambiguous-governed-api-key-shorthand",
        note="pricing wording that drops `governed` from the Rhumb API key path and blurs it with provider API keys",
        regex=re.compile(r"What is the difference between API key, wallet-prefund, and x402|(?<!Governed )API key and wallet-prefund both execute with X-Rhumb-Key|governed rail \(API key or wallet-prefund\)", re.IGNORECASE),
    ),
    DriftPattern(
        key="governed-api-key-label-shorthand",
        note="launch or onboarding labels that drop `governed` from the Rhumb API key path",
        regex=re.compile(r"For execution, pass your Rhumb API key:|Get an API key →|\*\*API key\*\* — sign up, get a key, prepaid credits|>API key</h3>|Execute via API key|BYOK, Agent Vault, API key, wallet-prefund, x402|Start with API key|account billing with API keys,|Create an API key for standard pricing|Get API key", re.IGNORECASE),
    ),
    DriftPattern(
        key="provider-keys-shorthand",
        note="Smithery migration wording that says generic `provider keys` instead of explicit provider API keys",
        regex=re.compile(r"Bring BYOK if you already have provider keys", re.IGNORECASE),
    ),
    DriftPattern(
        key="key-ownership-shorthand",
        note="Smithery migration wording that blurs credential ownership into `we hold keys / your keys` shorthand",
        regex=re.compile(r"Three credential paths:\s*Rhumb-managed \(we hold keys\), BYOK \(your keys\)", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class Match:
    pattern_key: str
    pattern_note: str
    path: Path
    line_number: int
    line: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional tracked file or directory paths relative to the repo root.",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include test files in the scan.",
    )
    return parser.parse_args()


def tracked_files(paths: Iterable[Path]) -> list[Path]:
    command = ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--"]
    command.extend(str(path) for path in paths)
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.decode("utf-8", errors="replace").strip(), file=sys.stderr)
        raise SystemExit(2) from exc

    raw = result.stdout.decode("utf-8", errors="replace")
    files = [Path(part) for part in raw.split("\0") if part]
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def should_scan(path: Path, include_tests: bool) -> bool:
    if any(part in SKIP_PARTS - {"tests"} for part in path.parts):
        return False
    if not include_tests and "tests" in path.parts:
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    return True


def scan_file(path: Path) -> list[Match]:
    full_path = REPO_ROOT / path
    try:
        text = full_path.read_text()
    except UnicodeDecodeError:
        return []
    except FileNotFoundError:
        return []

    matches: list[Match] = []
    for index, line in enumerate(text.splitlines(), start=1):
        for pattern in DRIFT_PATTERNS:
            if pattern.regex.search(line):
                matches.append(
                    Match(
                        pattern_key=pattern.key,
                        pattern_note=pattern.note,
                        path=path,
                        line_number=index,
                        line=line.strip(),
                    )
                )
    return matches


def print_matches(matches: list[Match]) -> None:
    print("AUD18_AUTHORITY_DRIFT")
    grouped: dict[str, list[Match]] = {}
    for match in matches:
        grouped.setdefault(match.pattern_key, []).append(match)

    order = {pattern.key: i for i, pattern in enumerate(DRIFT_PATTERNS)}
    for key in sorted(grouped, key=lambda item: order.get(item, 999)):
        pattern_matches = grouped[key]
        note = pattern_matches[0].pattern_note
        print(f"\n[{key}] {note}")
        for match in pattern_matches:
            print(f"- {match.path}:{match.line_number}: {match.line}")


def main() -> int:
    args = parse_args()
    scan_roots = tuple(Path(path) for path in args.paths) if args.paths else DEFAULT_SCAN_PATHS
    files = [path for path in tracked_files(scan_roots) if should_scan(path, args.include_tests)]
    matches: list[Match] = []
    for path in files:
        matches.extend(scan_file(path))

    if matches:
        print_matches(matches)
        return 1

    print("CLEAN_AUD18_AUTHORITY_SCAN")
    print(f"tracked_files_scanned={len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
