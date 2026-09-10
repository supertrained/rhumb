#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = ROOT / "docs" / "callable-contract.json"
CONTRACT_MD = ROOT / "docs" / "CALLABLE-CONTRACT.md"
DEFAULT_API_BASE = "https://api.rhumb.dev/v1"
USER_AGENT = "rhumb-verify/1.0"


class CallableContractError(ValueError):
    pass


@dataclass(frozen=True)
class CallableContract:
    fetched_at: str
    source: str
    services_registered: int
    services_callable: int
    services_registered_slugs: tuple[str, ...]
    services_callable_slugs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.fetched_at:
            raise CallableContractError("fetched_at is required")
        if not self.source:
            raise CallableContractError("source is required")
        if self.services_registered != len(self.services_registered_slugs):
            raise CallableContractError(
                "services_registered does not match len(services_registered_slugs)"
            )
        if self.services_callable != len(self.services_callable_slugs):
            raise CallableContractError(
                "services_callable does not match len(services_callable_slugs)"
            )
        if self.services_registered_slugs != tuple(sorted(set(self.services_registered_slugs))):
            raise CallableContractError("services_registered_slugs must be sorted unique")
        if self.services_callable_slugs != tuple(sorted(set(self.services_callable_slugs))):
            raise CallableContractError("services_callable_slugs must be sorted unique")
        if not set(self.services_callable_slugs).issubset(self.services_registered_slugs):
            raise CallableContractError("callable slugs must be a subset of registered slugs")


def _unwrap_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, Mapping):
        raise CallableContractError("payload data must be an object")
    return data


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CallableContractError(f"{field} must be a non-empty string")
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CallableContractError(f"{field} must be an int")
    return value


def _unique_sorted_slugs(raw: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise CallableContractError(f"{field} must be a list of strings")
    slugs: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item:
            raise CallableContractError(f"{field} must contain non-empty strings")
        if item in seen:
            raise CallableContractError(f"{field} contains duplicate slug {item!r}")
        seen.add(item)
        slugs.append(item)
    return tuple(sorted(slugs))


def _slugs_from_services(payload: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    data = _unwrap_data(payload)
    services = data.get("services")
    if not isinstance(services, list):
        raise CallableContractError("services payload is missing a services list")
    registered: list[str] = []
    callable_slugs: list[str] = []
    for item in services:
        if not isinstance(item, Mapping):
            raise CallableContractError("services list contains a non-object")
        slug = item.get("canonical_slug")
        if not isinstance(slug, str) or not slug:
            raise CallableContractError("services entry is missing canonical_slug")
        registered.append(slug)
        if item.get("callable") is True:
            callable_slugs.append(slug)
    return (
        _unique_sorted_slugs(registered, field="services_registered_slugs"),
        _unique_sorted_slugs(callable_slugs, field="services_callable_slugs"),
    )


def extract_from_stats(
    payload: Mapping[str, Any],
    *,
    fetched_at: str,
    source: str,
    services_fallback: Mapping[str, Any] | None = None,
) -> CallableContract:
    data = _unwrap_data(payload)
    has_registered = "services_registered_slugs" in data
    has_callable = "services_callable_slugs" in data
    if has_registered and has_callable:
        registered_slugs = _unique_sorted_slugs(
            data.get("services_registered_slugs"), field="services_registered_slugs"
        )
        callable_slugs = _unique_sorted_slugs(
            data.get("services_callable_slugs"), field="services_callable_slugs"
        )
    elif services_fallback is not None:
        registered_slugs, callable_slugs = _slugs_from_services(services_fallback)
    else:
        raise CallableContractError("stats payload is missing slug lists")

    registered_count = (
        _require_int(data["services_registered"], "services_registered")
        if "services_registered" in data
        else len(registered_slugs)
    )
    callable_count = (
        _require_int(data["services_callable"], "services_callable")
        if "services_callable" in data
        else len(callable_slugs)
    )
    return CallableContract(
        fetched_at=fetched_at,
        source=source,
        services_registered=registered_count,
        services_callable=callable_count,
        services_registered_slugs=registered_slugs,
        services_callable_slugs=callable_slugs,
    )


def contract_from_mapping(payload: Mapping[str, Any]) -> CallableContract:
    return CallableContract(
        fetched_at=_require_str(payload.get("fetched_at"), "fetched_at"),
        source=_require_str(payload.get("source"), "source"),
        services_registered=_require_int(payload.get("services_registered"), "services_registered"),
        services_callable=_require_int(payload.get("services_callable"), "services_callable"),
        services_registered_slugs=_unique_sorted_slugs(
            payload.get("services_registered_slugs"), field="services_registered_slugs"
        ),
        services_callable_slugs=_unique_sorted_slugs(
            payload.get("services_callable_slugs"), field="services_callable_slugs"
        ),
    )


def load_contract(path: Path) -> CallableContract:
    try:
        raw = json.loads(path.read_text())
    except OSError as exc:
        raise CallableContractError(f"failed to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CallableContractError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CallableContractError(f"{path} must contain a JSON object")
    return contract_from_mapping(raw)


def render_json(contract: CallableContract) -> str:
    payload = {
        "fetched_at": contract.fetched_at,
        "source": contract.source,
        "services_registered": contract.services_registered,
        "services_callable": contract.services_callable,
        "services_registered_slugs": list(contract.services_registered_slugs),
        "services_callable_slugs": list(contract.services_callable_slugs),
    }
    return json.dumps(payload, indent=2) + "\n"


def render_markdown(contract: CallableContract) -> str:
    callable_set = set(contract.services_callable_slugs)
    rows = "\n".join(
        f"| {slug} | {'yes' if slug in callable_set else 'no'} |"
        for slug in contract.services_registered_slugs
    )
    return (
        "# Callable contract\n"
        "\n"
        f"Snapshot dated `{contract.fetched_at}`.\n"
        "\n"
        "Live `GET /v1/proxy/stats` slug lists are the source of truth for registered "
        "and callable provider slugs. `circuits` is not inventory. Operators must not "
        "invent slugs.\n"
        "\n"
        f"Source: `{contract.source}`\n"
        "\n"
        f"Registered slugs: {contract.services_registered}. "
        f"Callable slugs: {contract.services_callable}.\n"
        "\n"
        "| slug | callable |\n"
        "| --- | --- |\n"
        f"{rows}\n"
    )


def write_snapshot(contract: CallableContract, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(render_json(contract))
    md_path.write_text(render_markdown(contract))


def write_markdown_from_json(json_path: Path, md_path: Path) -> CallableContract:
    contract = load_contract(json_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(contract))
    return contract


def check_contract(json_path: Path, md_path: Path) -> CallableContract:
    contract = load_contract(json_path)
    expected = render_markdown(contract)
    actual = md_path.read_text() if md_path.exists() else ""
    if actual != expected:
        raise CallableContractError(f"{md_path} is out of date with {json_path}")
    return contract


def fetch_json(url: str, timeout: float = 30) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected payload from {url}")
    return payload


def fetch_live_contract(api_base: str) -> CallableContract:
    stats_url = f"{api_base.rstrip('/')}/proxy/stats"
    stats = fetch_json(stats_url)
    data = _unwrap_data(stats)
    services_fallback = None
    if "services_registered_slugs" not in data or "services_callable_slugs" not in data:
        services_url = f"{api_base.rstrip('/')}/proxy/services"
        services_fallback = fetch_json(services_url)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return extract_from_stats(
        stats,
        fetched_at=fetched_at,
        source=stats_url,
        services_fallback=services_fallback,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lock live callable-contract slugs")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--from-live",
        action="store_true",
        help="Fetch live /proxy/stats and write docs/callable-contract.json plus CALLABLE-CONTRACT.md",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Validate the committed snapshot and fail if the markdown drifted",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Regenerate docs/CALLABLE-CONTRACT.md from the committed JSON",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("RHUMB_API_BASE", DEFAULT_API_BASE),
        help=f"Public API base used by --from-live (default {DEFAULT_API_BASE})",
    )
    args = parser.parse_args(argv)

    try:
        if args.from_live:
            contract = fetch_live_contract(args.api_base)
            write_snapshot(contract, CONTRACT_JSON, CONTRACT_MD)
            print(f"wrote {CONTRACT_JSON}")
            print(f"wrote {CONTRACT_MD}")
            return 0
        if args.check:
            check_contract(CONTRACT_JSON, CONTRACT_MD)
            print("Callable contract snapshot is up to date")
            return 0
        write_markdown_from_json(CONTRACT_JSON, CONTRACT_MD)
        print(f"wrote {CONTRACT_MD}")
        return 0
    except (CallableContractError, RuntimeError) as exc:
        print(f"Callable contract failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
