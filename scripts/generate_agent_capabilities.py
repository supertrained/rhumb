#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_TS = ROOT / "packages/mcp/src/server.ts"
PUBLIC_TRUTH_TS = ROOT / "packages/astro-web/src/lib/public-truth.ts"
OUTPUT_JSON = ROOT / "agent-capabilities.json"
WELL_KNOWN_OUTPUT_JSON = ROOT / "packages/astro-web/public/.well-known/agent-capabilities.json"
LLMS_TXT = ROOT / "llms.txt"
WEB_PUBLIC_LLMS_TXT = ROOT / "packages/web/public/llms.txt"
ROOT_README = ROOT / "README.md"
MCP_README = ROOT / "packages/mcp/README.md"

README_PRODUCT_START = "<!-- GENERATED:README_PRODUCT_SURFACE_START -->"
README_PRODUCT_END = "<!-- GENERATED:README_PRODUCT_SURFACE_END -->"
README_MCP_TOOLS_START = "<!-- GENERATED:README_MCP_TOOLS_START -->"
README_MCP_TOOLS_END = "<!-- GENERATED:README_MCP_TOOLS_END -->"
MCP_README_TOOL_SURFACE_START = "<!-- GENERATED:MCP_README_TOOL_SURFACE_START -->"
MCP_README_TOOL_SURFACE_END = "<!-- GENERATED:MCP_README_TOOL_SURFACE_END -->"


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
        "categories",
        "categoriesLabel",
        "callableProviders",
        "callableProvidersLabel",
        "mcpTools",
        "mcpToolsLabel",
        "domainsLabel",
        "beachheadLabel",
        "beachheadSummary",
        "trustOverviewUrl",
        "methodologyUrl",
        "providersUrl",
        "llmsUrl",
        "publicAgentCapabilitiesUrl",
        "currentSelfAssessmentUrl",
        "historicalSelfAssessmentUrl",
        "publicDisputeTemplateUrl",
        "publicDisputesUrl",
        "privateDisputesEmail",
        "privateDisputeMailto",
        "disputeResponseSlaBusinessDays",
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
        desc = ast.literal_eval(f'"{description}"')
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
        "description": f"Agent-native tool intelligence for {public_truth['beachheadLabel']} — discover, evaluate, and execute external tools with trust scores, failure modes, cost-aware routing, and managed credentials.",
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
            "categories": public_truth["categories"],
            "providers_with_execution": public_truth["callableProviders"],
            "credential_modes": ["byok", "rhumb_managed", "agent_vault"],
        },
        "scoring": {
            "methodology": public_truth["methodologyUrl"],
            "dimensions": 20,
            "axes": {
                "execution": {
                    "weight": 0.70,
                    "dimensions": 13,
                    "includes_autonomy_dimensions": 3,
                },
                "access": {"weight": 0.30, "dimensions": 7},
            },
            "tiers": {
                "L4_Native": "8.0-10.0",
                "L3_Ready": "6.0-7.9",
                "L2_Developing": "4.0-5.9",
                "L1_Emerging": "0.0-3.9",
            },
        },
        "trust": {
            "overview": public_truth["trustOverviewUrl"],
            "methodology": public_truth["methodologyUrl"],
            "provider_guide": public_truth["providersUrl"],
            "machine_readable_docs": public_truth["llmsUrl"],
            "agent_capabilities": public_truth["publicAgentCapabilitiesUrl"],
            "current_self_assessment": public_truth["currentSelfAssessmentUrl"],
            "historical_self_assessment": public_truth["historicalSelfAssessmentUrl"],
            "public_dispute_template": public_truth["publicDisputeTemplateUrl"],
            "public_dispute_log": public_truth["publicDisputesUrl"],
            "private_dispute_email": public_truth["privateDisputesEmail"],
            "private_dispute_mailto": public_truth["privateDisputeMailto"],
            "dispute_response_sla_business_days": public_truth["disputeResponseSlaBusinessDays"],
        },
        "pricing": {
            "discovery": "free",
            "execution": "prepaid_or_x402",
            "free_tier": "1000_calls_per_month",
            "details": "https://rhumb.dev/pricing",
        },
        "links": {
            "quickstart": "https://rhumb.dev/quickstart",
            "trust": public_truth["trustOverviewUrl"],
            "methodology": public_truth["methodologyUrl"],
            "providers": public_truth["providersUrl"],
            "blog": "https://rhumb.dev/blog",
            "github": "https://github.com/supertrained/rhumb",
            "disputes": public_truth["providersUrl"],
        },
    }


def render_tool_bullets(tool_names: list[str], tools: dict[str, str]) -> str:
    return "\n".join(f"- `{tool_name}` — {tools[tool_name]}" for tool_name in tool_names)


def render_tool_table(tool_names: list[str], tools: dict[str, str]) -> str:
    rows = ["| Tool | What it does |", "|------|-------------|"]
    rows.extend(f"| `{tool_name}` | {tools[tool_name]} |" for tool_name in tool_names)
    return "\n".join(rows)


def render_root_product_surface(public_truth: dict[str, int | str], tools: dict[str, str]) -> str:
    return f"""### Rhumb Index — Discover & Evaluate

**{public_truth['servicesLabel']} scored services** across {public_truth['domainsLabel']} domains. Each gets an [AN Score](https://rhumb.dev/methodology) (0–10) measuring execution quality, access readiness, and agent autonomy support.

{render_tool_bullets(GROUPS[0][3], tools)}

> Discovery breadth is wider than current execution coverage. The index is broader than what Rhumb can execute today.

### Rhumb Resolve — Execute

**{public_truth['capabilitiesLabel']} capability definitions** across **{public_truth['callableProvidersLabel']} callable providers today**. Cost-aware routing picks the best provider where execution is actually live.

- `execute_capability` — {tools['execute_capability']}
- `resolve_capability` — {tools['resolve_capability']}
- `estimate_capability` — {tools['estimate_capability']}
- `get_receipt` — {tools['get_receipt']}
- Budget enforcement, credential management, and execution telemetry included

> Best current fit: {public_truth['beachheadLabel']}. Treat general business-agent automation and broad multi-system orchestration as future scope, not the current launch promise."""


def render_root_mcp_tools(public_truth: dict[str, int | str], tools: dict[str, str]) -> str:
    sections: list[str] = [f"`rhumb-mcp` exposes **{public_truth['mcpToolsLabel']} tools**:"]
    for group_name, _, _, tool_names in GROUPS:
        title = group_name.capitalize()
        sections.append(f"\n**{title}**\n{render_tool_bullets(tool_names, tools)}")
    sections.append(
        f"\n> Discovery spans {public_truth['servicesLabel']} scored services, but current governed execution spans {public_truth['callableProvidersLabel']} callable providers."
    )
    sections.append(
        "\n> Note: Layer 3 recipe tooling is live, but the public catalog can still be empty. Use `rhumb_list_recipes` or visit `/recipes` before assuming a workflow exists."
    )
    sections.append(
        f"\n> Best current fit: {public_truth['beachheadLabel']}. Treat general business-agent automation as future scope, not the current launch promise."
    )
    return "\n".join(sections)


def render_mcp_readme_tool_surface(public_truth: dict[str, int | str], tools: dict[str, str]) -> str:
    sections: list[str] = []
    sections.append(f"## Discovery tools (no auth, {len(GROUPS[0][3])} tools)\n\n{render_tool_table(GROUPS[0][3], tools)}")
    sections.append(f"## Execution tools (auth required, {len(GROUPS[1][3])} tools)\n\n```json\n{{\n  \"mcpServers\": {{\n    \"rhumb\": {{\n      \"command\": \"npx\",\n      \"args\": [\"-y\", \"rhumb-mcp@latest\"],\n      \"env\": {{\n        \"RHUMB_API_KEY\": \"rk_your_key_here\"\n      }}\n    }}\n  }}\n}}\n```\n\nGet a key at https://rhumb.dev/auth/login (GitHub, Google, or email — 30 seconds).\n\n{render_tool_table(GROUPS[1][3], tools)}")
    sections.append(f"## Financial tools (auth required, {len(GROUPS[2][3])} tools)\n\n{render_tool_table(GROUPS[2][3], tools)}")
    sections.append(f"## Operations tools (auth required, {len(GROUPS[3][3])} tools)\n\n{render_tool_table(GROUPS[3][3], tools)}")
    sections.append(
        f"## {public_truth['mcpToolsLabel']} MCP tools\n\n"
        f"**Discovery (free):** {', '.join(f'`{name}`' for name in GROUPS[0][3])}\n\n"
        f"**Execution (auth):** {', '.join(f'`{name}`' for name in GROUPS[1][3])}\n\n"
        f"**Financial (auth):** {', '.join(f'`{name}`' for name in GROUPS[2][3])}\n\n"
        f"**Operations (auth):** {', '.join(f'`{name}`' for name in GROUPS[3][3])}\n\n"
        f"> Discovery spans {public_truth['servicesLabel']} scored services, but current governed execution spans {public_truth['callableProvidersLabel']} callable providers.\n\n"
        f"> Best current fit: {public_truth['beachheadLabel']}. Treat general business-agent automation as future scope, not the current launch promise."
    )
    return "\n\n".join(sections)


def render_llms_txt(public_truth: dict[str, int | str], tools: dict[str, str]) -> str:
    return f"""# Rhumb — Agent-Native Tool Intelligence
> Canonical public docs: https://rhumb.dev/llms.txt

## What is Rhumb?
Rhumb is agent-native tool intelligence: discover, evaluate, and execute external tools with trust scores, failure modes, cost-aware routing, and managed credentials.

## Current launchable scope
- Best current fit: {public_truth['beachheadLabel']}
- Not the current promise: general business-agent automation or broad multi-system workflow orchestration

## Primary surfaces
- Website: https://rhumb.dev
- API: https://api.rhumb.dev/v1
- MCP: npx rhumb-mcp@latest
- npm: https://www.npmjs.com/package/rhumb-mcp

## Current coverage
- {public_truth['servicesLabel']} scored services across {public_truth['domainsLabel']} domains
- {public_truth['capabilitiesLabel']} capability definitions
- {public_truth['categoriesLabel']} categories
- {public_truth['callableProvidersLabel']} callable providers
- {public_truth['mcpToolsLabel']} MCP tools
- 3 credential modes: BYOK, Rhumb-managed, Agent Vault

## Honest current state
- Discovery breadth is wider than execution breadth
- The index covers {public_truth['servicesLabel']} scored services and {public_truth['capabilitiesLabel']} capability definitions
- Current governed execution surface is {public_truth['callableProvidersLabel']} callable providers
- Best current fit remains {public_truth['beachheadLabel']}

## Discovery (no auth)
- GET https://api.rhumb.dev/v1/search?q={{query}} — search services
- GET https://api.rhumb.dev/v1/services/{{slug}}/score — AN Score breakdown
- GET https://api.rhumb.dev/v1/services/{{slug}}/failures — known failure modes
- GET https://api.rhumb.dev/v1/capabilities — browse capability registry
- GET https://api.rhumb.dev/v1/capabilities/{{id}}/resolve — ranked providers
- GET https://api.rhumb.dev/v1/leaderboard/{{category}} — category rankings
- GET https://api.rhumb.dev/v1/telemetry/provider-health — provider health status
- GET https://api.rhumb.dev/v1/pricing — machine-readable pricing

## Execution (requires API key or x402 payment)
- POST https://api.rhumb.dev/v1/capabilities/{{id}}/execute — execute a capability
- GET https://api.rhumb.dev/v1/capabilities/{{id}}/execute/estimate — estimate the active execution rail, cost, and health before execution; anonymous direct system-of-record paths also preserve machine-readable execute_readiness handoffs

## Auth paths
1. API key: sign up at https://rhumb.dev/auth/login, send X-Rhumb-Key header
2. x402 / USDC: no signup, pay per call, send X-Payment header
3. BYOK credentials: pass your own upstream API keys

## MCP tools ({public_truth['mcpToolsLabel']} total)
Discovery: {', '.join(GROUPS[0][3])}
Execution: {', '.join(GROUPS[1][3])}
Billing: {', '.join(GROUPS[2][3])}
Operations: {', '.join(GROUPS[3][3])}

## Key tool semantics
- find_services — {tools['find_services']}
- get_score — {tools['get_score']}
- resolve_capability — {tools['resolve_capability']}
- execute_capability — {tools['execute_capability']}
- estimate_capability — {tools['estimate_capability']}
- get_receipt — {tools['get_receipt']}
- usage_telemetry — {tools['usage_telemetry']}

## Pricing
- Discovery: free, no auth
- Execution: governed API key, wallet-prefund, x402 per-call, or BYOK
- No subscriptions, no seat fees, no minimums
- Live pricing and markup terms: https://rhumb.dev/pricing

## Trust and disputes
- Trust overview: {public_truth['trustOverviewUrl']}
- Methodology: {public_truth['methodologyUrl']}
- Current self-assessment: {public_truth['currentSelfAssessmentUrl']}
- Historical baseline: {public_truth['historicalSelfAssessmentUrl']}
- Provider guide and dispute process: {public_truth['providersUrl']}
- Public dispute template: {public_truth['publicDisputeTemplateUrl']}
- Public dispute log: {public_truth['publicDisputesUrl']}
- Private disputes: {public_truth['privateDisputeMailto']}
- Dispute response target: {public_truth['disputeResponseSlaBusinessDays']} business days

## Links
- Quickstart: https://rhumb.dev/quickstart
- Pricing: https://rhumb.dev/pricing
- Blog: https://rhumb.dev/blog
- GitHub: https://github.com/supertrained/rhumb
- Public agent capabilities: {public_truth['publicAgentCapabilitiesUrl']}""" + "\n"


def replace_managed_block(text: str, start_marker: str, end_marker: str, body: str) -> str:
    pattern = re.compile(rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}", re.S)
    if not pattern.search(text):
        raise RuntimeError(f"Missing managed block markers: {start_marker} ... {end_marker}")
    replacement = f"{start_marker}\n{body.rstrip()}\n{end_marker}"
    return pattern.sub(replacement, text, count=1)


def build_readme_outputs(public_truth: dict[str, int | str], tools: dict[str, str]) -> dict[Path, str]:
    agent_contract = json.dumps(build_agent_capabilities(), indent=2, ensure_ascii=False) + "\n"

    root_readme = ROOT_README.read_text()
    root_readme = replace_managed_block(
        root_readme,
        README_PRODUCT_START,
        README_PRODUCT_END,
        render_root_product_surface(public_truth, tools),
    )
    root_readme = replace_managed_block(
        root_readme,
        README_MCP_TOOLS_START,
        README_MCP_TOOLS_END,
        render_root_mcp_tools(public_truth, tools),
    )

    mcp_readme = MCP_README.read_text()
    mcp_readme = replace_managed_block(
        mcp_readme,
        MCP_README_TOOL_SURFACE_START,
        MCP_README_TOOL_SURFACE_END,
        render_mcp_readme_tool_surface(public_truth, tools),
    )

    llms_txt = render_llms_txt(public_truth, tools)

    return {
        OUTPUT_JSON: agent_contract,
        WELL_KNOWN_OUTPUT_JSON: agent_contract,
        LLMS_TXT: llms_txt,
        WEB_PUBLIC_LLMS_TXT: llms_txt,
        ROOT_README: root_readme,
        MCP_README: mcp_readme,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate public truth surfaces from live repo truth")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated truth surfaces are out of date")
    parser.add_argument("--write", action="store_true", help="Write generated truth surfaces to disk")
    args = parser.parse_args()

    public_truth = load_public_truth()
    tools = extract_tools()
    rendered_files = build_readme_outputs(public_truth, tools)

    if args.check:
        stale_files = []
        for path, rendered in rendered_files.items():
            current = path.read_text() if path.exists() else ""
            if current != rendered:
                stale_files.append(path.relative_to(ROOT).as_posix())
        if stale_files:
            print("Generated truth surfaces are out of date:")
            for path in stale_files:
                print(f"- {path}")
            return 1
        print("Generated truth surfaces are up to date")
        return 0

    if args.write:
        for path, rendered in rendered_files.items():
            path.write_text(rendered)
            print(f"wrote {path}")
        return 0

    print(rendered_files[OUTPUT_JSON], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
