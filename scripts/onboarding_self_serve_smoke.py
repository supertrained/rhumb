#!/usr/bin/env python3
"""Self-serve onboarding smoke helper (session-auth).

Goal: exercise the user-facing onboarding control-plane without admin/operator help:
- email OTP login (session cookie)
- billing snapshot
- Stripe checkout session creation
- auto-reload enable
- secondary agent key creation
- first successful execute call using the new key

This is an interactive script (prompts for OTP code + asks you to complete Checkout).

Usage:
  python3 scripts/onboarding_self_serve_smoke.py --email you@example.com

Environment:
  RHUMB_API_BASE (optional) defaults to https://api.rhumb.dev
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_API_BASE = "https://api.rhumb.dev"
DEFAULT_CHECKOUT_AMOUNT_USD = 25.0
DEFAULT_AUTO_RELOAD_THRESHOLD_USD = 10.0
DEFAULT_AUTO_RELOAD_AMOUNT_USD = 50.0
DEFAULT_SECONDARY_BUDGET_USD = 10.0
DEFAULT_SECONDARY_RATE_LIMIT_QPM = 20
DEFAULT_FIRST_CALL_CAPABILITY = "search.query"
DEFAULT_FIRST_CALL_CREDENTIAL_MODE = "rhumb_managed"


@dataclass
class SmokeResult:
    api_base: str
    email: str
    has_payment_method: bool
    balance_usd: float
    auto_reload_enabled: bool | None = None
    secondary_agent_id: str | None = None
    secondary_api_key_prefix: str | None = None
    first_call_ok: bool | None = None


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or "").strip() or default


def _print_json(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2) + "\n")


def _extract_session_token(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("session_token")
    return str(token) if token else None


def _pick_preferred_provider(resolve_payload: Any) -> str | None:
    if not isinstance(resolve_payload, dict):
        return None
    data = resolve_payload.get("data")
    if not isinstance(data, dict):
        return None

    hint = data.get("execute_hint")
    if isinstance(hint, dict) and hint.get("preferred_provider"):
        return str(hint["preferred_provider"])

    providers = data.get("providers")
    if isinstance(providers, list) and providers:
        first = providers[0]
        if isinstance(first, dict) and first.get("service_slug"):
            return str(first["service_slug"])

    return None


def _build_search_query_body(query: str) -> dict[str, Any]:
    # Kept intentionally minimal; API examples + tests show nested {"body": {...}}.
    return {"q": query}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-base", default=_env("RHUMB_API_BASE", DEFAULT_API_BASE))
    ap.add_argument("--email", required=True)
    ap.add_argument("--otp", help="OTP code (if omitted, you'll be prompted)")
    ap.add_argument("--checkout-amount-usd", type=float, default=DEFAULT_CHECKOUT_AMOUNT_USD)
    ap.add_argument("--skip-checkout", action="store_true", help="Do not create a Stripe Checkout session")
    ap.add_argument("--poll-seconds", type=int, default=90)
    ap.add_argument("--poll-interval", type=float, default=3.0)

    ap.add_argument("--enable-auto-reload", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--auto-reload-threshold-usd", type=float, default=DEFAULT_AUTO_RELOAD_THRESHOLD_USD)
    ap.add_argument("--auto-reload-amount-usd", type=float, default=DEFAULT_AUTO_RELOAD_AMOUNT_USD)

    ap.add_argument("--create-secondary", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--secondary-name", default="Secondary Agent")
    ap.add_argument("--secondary-description", default="Onboarding smoke secondary key")
    ap.add_argument("--secondary-budget-usd", type=float, default=DEFAULT_SECONDARY_BUDGET_USD)
    ap.add_argument("--secondary-rate-limit-qpm", type=int, default=DEFAULT_SECONDARY_RATE_LIMIT_QPM)

    ap.add_argument("--first-call", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--first-call-capability", default=DEFAULT_FIRST_CALL_CAPABILITY)
    ap.add_argument("--first-call-query", default="Rhumb onboarding smoke test")
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    return ap


def main() -> int:
    args = build_parser().parse_args()

    api_base = str(args.api_base).rstrip("/")
    email = str(args.email).strip()
    if not email:
        raise SystemExit("--email is required")

    timeout = httpx.Timeout(30.0)

    # 1) Request OTP
    with httpx.Client(timeout=timeout) as client:
        req = client.post(
            f"{api_base}/v1/auth/email/request-code",
            json={"email": email},
            headers={"User-Agent": "rhumb/scripts/onboarding_self_serve_smoke.py"},
        )
    if req.status_code != 200:
        raise SystemExit(f"OTP request failed: HTTP {req.status_code}: {req.text[:300]}")

    otp = (args.otp or "").strip() or input("Enter the OTP code from your email: ").strip()
    if not otp:
        raise SystemExit("No OTP code provided")

    # 2) Verify OTP -> session token
    with httpx.Client(timeout=timeout) as client:
        verify = client.post(
            f"{api_base}/v1/auth/email/verify-code",
            json={"email": email, "code": otp},
            headers={"User-Agent": "rhumb/scripts/onboarding_self_serve_smoke.py"},
        )
    if verify.status_code != 200:
        raise SystemExit(f"OTP verify failed: HTTP {verify.status_code}: {verify.text[:300]}")

    session_token = _extract_session_token(verify.json())
    if not session_token:
        raise SystemExit("Verify response missing session_token")

    cookies = {"rhumb_session": session_token}

    # 3) Billing snapshot
    with httpx.Client(timeout=timeout, cookies=cookies) as client:
        billing = client.get(f"{api_base}/v1/auth/me/billing")
    if billing.status_code != 200:
        raise SystemExit(f"/v1/auth/me/billing failed: HTTP {billing.status_code}: {billing.text[:300]}")

    billing_data = billing.json()
    has_payment = bool(billing_data.get("has_payment_method"))
    balance = float(billing_data.get("balance_usd") or 0.0)

    # 4) Checkout (interactive)
    if not args.skip_checkout and not has_payment:
        with httpx.Client(timeout=timeout, cookies=cookies) as client:
            checkout = client.post(
                f"{api_base}/v1/auth/me/billing/checkout",
                json={"amount_usd": float(args.checkout_amount_usd)},
            )
        if checkout.status_code != 200:
            raise SystemExit(
                f"/v1/auth/me/billing/checkout failed: HTTP {checkout.status_code}: {checkout.text[:300]}"
            )

        checkout_payload = checkout.json() if checkout.headers.get("content-type", "").startswith("application/json") else {}
        checkout_url = checkout_payload.get("checkout_url")
        sys.stdout.write(f"\nOpen Stripe Checkout and complete payment:\n{checkout_url}\n\n")
        input("Press Enter after you complete Checkout and return to the dashboard... ")

        deadline = time.time() + int(args.poll_seconds)
        while time.time() < deadline:
            with httpx.Client(timeout=timeout, cookies=cookies) as client:
                billing = client.get(f"{api_base}/v1/auth/me/billing")
            if billing.status_code == 200:
                billing_data = billing.json()
                has_payment = bool(billing_data.get("has_payment_method"))
                balance = float(billing_data.get("balance_usd") or 0.0)
                if has_payment and balance > 0:
                    break
            time.sleep(float(args.poll_interval))

    # 5) Enable auto-reload
    auto_reload_enabled: bool | None = None
    if args.enable_auto_reload:
        with httpx.Client(timeout=timeout, cookies=cookies) as client:
            resp = client.put(
                f"{api_base}/v1/auth/me/billing/auto-reload",
                json={
                    "enabled": True,
                    "threshold_usd": float(args.auto_reload_threshold_usd),
                    "amount_usd": float(args.auto_reload_amount_usd),
                },
            )
        if resp.status_code != 200:
            raise SystemExit(
                f"/v1/auth/me/billing/auto-reload failed: HTTP {resp.status_code}: {resp.text[:300]}"
            )
        auto_reload_enabled = bool(resp.json().get("auto_reload_enabled"))

    secondary_agent_id: str | None = None
    secondary_key: str | None = None
    secondary_prefix: str | None = None

    # 6) Create a secondary agent key
    if args.create_secondary:
        with httpx.Client(timeout=timeout, cookies=cookies) as client:
            resp = client.post(
                f"{api_base}/v1/auth/me/agents",
                json={
                    "name": str(args.secondary_name),
                    "description": str(args.secondary_description),
                    "budget_usd": float(args.secondary_budget_usd),
                    "period": "monthly",
                    "hard_limit": True,
                    "rate_limit_qpm": int(args.secondary_rate_limit_qpm),
                },
            )
        if resp.status_code != 200:
            raise SystemExit(f"/v1/auth/me/agents failed: HTTP {resp.status_code}: {resp.text[:300]}")

        payload = resp.json()
        secondary_agent_id = payload.get("agent_id")
        secondary_key = payload.get("api_key")
        secondary_prefix = payload.get("api_key_prefix")
        if not secondary_agent_id or not secondary_key:
            raise SystemExit("Create secondary agent response missing agent_id/api_key")

        sys.stdout.write(
            "\nSecondary agent key created. Save it now (it won't be shown again):\n"
            f"agent_id: {secondary_agent_id}\n"
            f"key_prefix: {secondary_prefix}\n\n"
        )

    # 7) First successful call
    first_call_ok: bool | None = None
    if args.first_call and secondary_key:
        capability = str(args.first_call_capability)

        with httpx.Client(timeout=timeout) as client:
            resolve = client.get(
                f"{api_base}/v1/capabilities/{capability}/resolve",
                params={"credential_mode": DEFAULT_FIRST_CALL_CREDENTIAL_MODE},
                headers={"X-Rhumb-Key": secondary_key},
            )
        if resolve.status_code != 200:
            raise SystemExit(f"resolve failed: HTTP {resolve.status_code}: {resolve.text[:300]}")

        preferred_provider = _pick_preferred_provider(resolve.json())
        if not preferred_provider:
            raise SystemExit("resolve response missing preferred provider")

        with httpx.Client(timeout=timeout) as client:
            execute = client.post(
                f"{api_base}/v1/capabilities/{capability}/execute",
                headers={"X-Rhumb-Key": secondary_key},
                json={
                    "provider": preferred_provider,
                    "credential_mode": DEFAULT_FIRST_CALL_CREDENTIAL_MODE,
                    "body": _build_search_query_body(str(args.first_call_query)),
                    "interface": "onboarding_smoke",
                },
            )

        first_call_ok = execute.status_code == 200
        if not first_call_ok:
            raise SystemExit(f"first call failed: HTTP {execute.status_code}: {execute.text[:500]}")

        sys.stdout.write(f"First call OK (provider={preferred_provider}, capability={capability}).\n")

    result = SmokeResult(
        api_base=api_base,
        email=email,
        has_payment_method=has_payment,
        balance_usd=balance,
        auto_reload_enabled=auto_reload_enabled,
        secondary_agent_id=secondary_agent_id,
        secondary_api_key_prefix=secondary_prefix,
        first_call_ok=first_call_ok,
    )

    if args.json:
        _print_json(result.__dict__)
    else:
        sys.stdout.write("\nSummary:\n")
        _print_json(result.__dict__)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
