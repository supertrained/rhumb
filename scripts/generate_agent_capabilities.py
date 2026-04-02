#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_TS = ROOT / "packages/mcp/src/server.ts"
PUBLIC_TRUTH_TS = ROOT / "packages/astro-web/src/lib/public-truth.ts"
OUTPUT_JSON = ROOT / "agent-capabilities.json"


GROUPS: list[tuple[str, str, bool, list[str]]] = [
    (
        "discovery",
        "Search, score, and evaluate {services_label} services across 50+ domains",
        False,
        [
            "find_services",
            "get_score",
            "get_alternatives",
            "get_failure_modes",
            "discover_capabilities",
            "resolve_capability",
        ],
    ),
    (
        "execution",
        "Execute capabilities through Resolve with managed auth and cost-aware routing",
        True,
        [
            "execute_capability",
            "estimate_capability",
            "credential_ceremony",
            "check_credentials",
            "rhumb_list_recipes",
            "rhumb_get_recipe",
            "rhumb_recipe_execute",
            "get_receipt",
        ],
    ),
    (
        "billing",
        "Budget enforcement and spend tracking",
        True,
        [
            "budget",
            "spend",
            "check_balance",
            "get_payment_url",
            "get_ledger",
        ],
    ),
    (
        "operations",
        "Routing preferences and usage analytics",
        True,
        ["routing", "usage_telemetry"],
    ),
]


def load_public_truth() -> dict[str, int | str]:
    text = PUBLIC_TRUTH_TS.read_text()
    out: dict[str, int | str] = {}
    for key in [
        "services",
        "servicesLabel",
        "capabilities",
        "capabilitiesLabel",
        "callableProviders",
        "callableProvidersLabel",
        "mcpTools",
        "mcpToolsLabel",
        "domainsLabel",
    ]:
        match = re.search(rf"{re.escape(key)}:\s*(\d+|\"[^\"]+\")", text)
        if not match:
            raise RuntimeError(f"Missing {key} in {PUBLIC_TRUTH_TS}")
        raw = match.group(1)
        out[key] = int(raw) if raw.isdigit() else raw.strip('"')
    return out


def extract_tools() -> dict[str, str]:
    text = SERVER_TS.read_text()
    pattern = re.compile(
        r'server\.tool\(\s*\n\s*"([^"]+)"\s*,\s*\n\s*"((?:[^"\\]|\\.)*)"',
        re.S,
    )
    tools: dict[str, str] = {}
    for name, description in pattern.findall(text):
        desc = bytes(description, "utf-8").decode("unicode_escape")
        tools[name] = desc.split(". ", 1)[0].strip().rstrip(".")
    if len(tools) != 21:
        raise RuntimeError(f"Expected 21 MCP tools from {SERVER_TS}, got {len(tools)}")
    return tools


def build_agent_capabilities() -> dict:
    public_truth = load_public_truth()
    tools = extract_tools()

    capabilities: dict[str, dict] = {}
    for group_name, description_template, auth_required, tool_names in GROUPS:
        capabilities[group_name] = {
            "description": description_template.format(services_label=public_truth["servicesLabel"]),
            "auth_required": auth_required,
            "tools": [
                {"name": tool_name, "description": tools[tool_name]}
                for tool_name in tool_names
            ],
        }

    return {
        "schema_version": "1.0",
        "name": "Rhumb",
        "description": "Agent-native tool intelligence — discover, evaluate, and execute external tools with trust scores, failure modes, cost-aware routing, and managed credentials.",
        "homepage": "https://rhumb.dev",
        "api_base": "https://api.rhumb.dev/v1",
        "mcp_install": "npx rhumb-mcp@latest",
        "npm_package": "rhumb-mcp",
        "auth": {
            "discovery": "none",
            "execution": "api_key_or_x402",
            "signup_url": "https://rhumb.dev/auth/login",
        },
        "capabilities": capabilities,
        "coverage": {
            "services": public_truth["services"],
            "capabilities": public_truth["capabilities"],
            "domains": 50,
            "categories": 92,
            "providers_with_execution": public_truth["callableProviders"],
            "credential_modes": ["byo", "rhumb_managed", "agent_vault"],
        },
        "scoring": {
            "methodology": "https://rhumb.dev/methodology",
            "dimensions": 20,
            "axes": {
                "execution": {"weight": 0.45, "dimensions": 17},
                "access": {"weight": 0.40, "dimensions": 6},
                "autonomy": {"weight": 0.15, "dimensions": 3},
            },
            "tiers": {
                "L4_Native": "8.0-10.0",
                "L3_Ready": "6.0-7.9",
                "L2_Developing": "4.0-5.9",
                "L1_Emerging": "0.0-3.9",
            },
        },
        "pricing": {
            "discovery": "free",
            "execution": "prepaid_or_x402",
            "free_tier": "1000_calls_per_month",
            "details": "https://rhumb.dev/pricing",
        },
        "links": {
            "quickstart": "https://rhumb.dev/quickstart",
            "trust": "https://rhumb.dev/trust",
            "methodology": "https://rhumb.dev/methodology",
            "blog": "https://rhumb.dev/blog",
            "github": "https://github.com/supertrained/rhumb",
            "disputes": "https://github.com/supertrained/rhumb/issues",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate agent-capabilities.json from live repo truth")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if agent-capabilities.json is out of date")
    parser.add_argument("--write", action="store_true", help="Write the generated JSON to agent-capabilities.json")
    args = parser.parse_args()

    rendered = json.dumps(build_agent_capabilities(), indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = OUTPUT_JSON.read_text() if OUTPUT_JSON.exists() else ""
        if current != rendered:
            print("agent-capabilities.json is out of date")
            return 1
        print("agent-capabilities.json is up to date")
        return 0

    if args.write:
        OUTPUT_JSON.write_text(rendered)
        print(f"wrote {OUTPUT_JSON}")
        return 0

    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
