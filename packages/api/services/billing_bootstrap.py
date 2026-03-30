"""Billing bootstrap helpers for launch/dashboard orgs.

Ensures the billing-side org + wallet rows exist for authenticated dashboard users,
and optionally seeds a small starter balance for first-run verification flows.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings
from schemas.user import (
    EMAIL_NO_TRIAL_CREDIT_POLICY,
    EMAIL_OTP_SIGNUP_METHOD,
    OAUTH_SIGNUP_METHOD,
    OAUTH_TRIAL_CREDIT_POLICY,
)
from services.payment_metrics import log_payment_event

logger = logging.getLogger(__name__)


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _sb_url(path: str) -> str:
    return f"{settings.supabase_url}/rest/v1/{path}"


async def _sb_get(path: str) -> Any | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(_sb_url(path), headers=_sb_headers(), timeout=10.0)
        if resp.status_code != 200:
            logger.warning("Supabase GET %s failed: %s %s", path, resp.status_code, resp.text)
            return None
        return resp.json()


async def _sb_post(path: str, payload: dict[str, Any], *, prefer: str = "return=representation") -> Any | None:
    headers = {**_sb_headers(), "Prefer": prefer}
    async with httpx.AsyncClient() as client:
        resp = await client.post(_sb_url(path), headers=headers, json=payload, timeout=10.0)
        if resp.status_code not in (200, 201):
            logger.warning("Supabase POST %s failed: %s %s", path, resp.status_code, resp.text)
            return None
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}


def _resolve_starter_credits_cents(
    *,
    starter_credits_cents: int | None,
    signup_method: str,
    credit_policy: str,
) -> int:
    """Return the starter credit amount allowed by auth/signup policy."""
    requested_cents = (
        settings.billing_bootstrap_starter_credits_cents
        if starter_credits_cents is None
        else starter_credits_cents
    )

    if (
        signup_method == EMAIL_OTP_SIGNUP_METHOD
        or credit_policy == EMAIL_NO_TRIAL_CREDIT_POLICY
    ):
        return 0

    if starter_credits_cents is None and credit_policy != OAUTH_TRIAL_CREDIT_POLICY:
        return 0

    return max(0, requested_cents)


async def ensure_org_billing_bootstrap(
    org_id: str,
    *,
    email: str | None = None,
    name: str | None = None,
    starter_credits_cents: int | None = None,
    signup_method: str = OAUTH_SIGNUP_METHOD,
    credit_policy: str = OAUTH_TRIAL_CREDIT_POLICY,
) -> dict[str, Any]:
    """Ensure ``orgs`` + ``org_credits`` rows exist for an org.

    Idempotent for the steady state:
    - Missing ``orgs`` row -> create it
    - Missing ``org_credits`` row -> create it
    - First wallet creation can seed a starter balance once

    ``email`` may be None for wallet-linked pseudonymous orgs.
    """
    starter_cents = _resolve_starter_credits_cents(
        starter_credits_cents=starter_credits_cents,
        signup_method=signup_method,
        credit_policy=credit_policy,
    )
    display_name = (
        name
        or (email.split("@", 1)[0] if email else None)
        or org_id
    ).strip() or org_id

    result = {
        "org_created": False,
        "wallet_created": False,
        "seeded_credits_cents": 0,
    }

    existing_orgs = await _sb_get(f"orgs?id=eq.{org_id}&select=id&limit=1")
    if not existing_orgs:
        org_payload: dict[str, Any] = {
            "id": org_id,
            "name": display_name,
            "tier": "free",
        }
        if email is not None:
            org_payload["email"] = email
        created = await _sb_post(
            "orgs",
            org_payload,
            prefer="return=minimal",
        )
        if created is not None:
            result["org_created"] = True

    existing_wallets = await _sb_get(f"org_credits?org_id=eq.{org_id}&select=org_id&limit=1")
    if existing_wallets:
        return result

    created_wallet = await _sb_post(
        "org_credits",
        {
            "org_id": org_id,
            "balance_usd_cents": starter_cents,
        },
        prefer="return=minimal",
    )
    if created_wallet is None:
        return result

    result["wallet_created"] = True
    result["seeded_credits_cents"] = starter_cents

    if starter_cents > 0:
        await _sb_post(
            "credit_ledger",
            {
                "org_id": org_id,
                "event_type": "credit_added",
                "amount_usd_cents": starter_cents,
                "balance_after_usd_cents": starter_cents,
                "description": "Starter credits via dashboard/org bootstrap",
                "metadata": {
                    "source": "billing_bootstrap",
                    "bootstrap": True,
                    "signup_method": signup_method,
                    "credit_policy": credit_policy,
                    "starter_credits_seeded": True,
                },
            },
            prefer="return=minimal",
        )
        log_payment_event(
            "bootstrap_credits_seeded",
            org_id=org_id,
            amount_usd_cents=starter_cents,
            provider="internal",
        )
    else:
        logger.info(
            "Billing bootstrap created wallet without starter credits for org %s "
            "(signup_method=%s, credit_policy=%s)",
            org_id,
            signup_method,
            credit_policy,
        )

    return result
