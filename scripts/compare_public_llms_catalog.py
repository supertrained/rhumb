#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


DEFAULT_API_BASE = os.environ.get("RHUMB_API_BASE", "https://api.rhumb.dev/v1")
DEFAULT_LLMS_URL = os.environ.get("RHUMB_LLMS_URL", "https://rhumb.dev/llms.txt")


def _get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "rhumb-verify/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode())
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected payload from {url}")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected data envelope from {url}")
    return data


def _get_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "rhumb-verify/1.0", "Accept": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def fetch_api_catalog(api_base: str) -> tuple[set[str], set[str], int]:
    meta = _get_json(f"{api_base.rstrip('/')}/services?limit=1")
    total = int(meta["total"])
    slugs: set[str] = set()
    categories: set[str] = set()
    offset = 0
    limit = 500
    while offset < total:
        page = _get_json(f"{api_base.rstrip('/')}/services?limit={limit}&offset={offset}")
        items = page.get("items") or []
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if isinstance(slug, str) and slug:
                slugs.add(slug)
            category = item.get("category")
            if isinstance(category, str) and category:
                categories.add(category)
        offset += len(items)
    return slugs, categories, total


def parse_llms(text: str) -> tuple[int | None, set[str], set[str]]:
    header = re.search(r"## Scored Services \((\d+) total\)", text)
    scored = int(header.group(1)) if header else None
    slugs = set(re.findall(r"^- /service/([^\s]+) —", text, re.M))
    categories = set(re.findall(r"^- /leaderboard/([a-z0-9-]+) \(", text, re.M))
    return scored, slugs, categories


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare generated llms.txt service/category sets to the live scored API"
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--llms-url", default=DEFAULT_LLMS_URL)
    parser.add_argument("--llms-file", help="Compare a local llms.txt instead of fetching --llms-url")
    args = parser.parse_args()

    api_slugs, api_categories, api_total = fetch_api_catalog(args.api_base)
    llms_text = Path(args.llms_file).read_text(encoding="utf-8") if args.llms_file else _get_text(args.llms_url)
    scored_header, llms_slugs, llms_categories = parse_llms(llms_text)

    llms_only = sorted(llms_slugs - api_slugs)
    api_only = sorted(api_slugs - llms_slugs)
    missing_cats = sorted(api_categories - llms_categories)
    extra_cats = sorted(llms_categories - api_categories)

    report = {
        "api_services_total": api_total,
        "api_slug_count": len(api_slugs),
        "api_category_count": len(api_categories),
        "llms_scored_header": scored_header,
        "llms_service_lines": len(llms_slugs),
        "llms_category_lines": len(llms_categories),
        "llms_only_slugs": llms_only,
        "api_only_slugs": api_only,
        "llms_missing_categories": missing_cats,
        "llms_extra_categories": extra_cats,
    }
    print(json.dumps(report, indent=2))
    if (
        scored_header != api_total
        or llms_slugs != api_slugs
        or llms_categories != api_categories
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
