"""Payment system health indicators."""

from __future__ import annotations

import logging
import os

import httpx

from config import settings

logger = logging.getLogger(__name__)

_BILLING_HEALTH_PATH = "org_credits?select=org_id&limit=1"

BASE_MAINNET_RPC = "https://mainnet.base.org"


def _billing_headers(supabase_key: str) -> dict[str, str]:
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }


async def _probe_billing_health(supabase_url: str, supabase_key: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{supabase_url}/rest/v1/{_BILLING_HEALTH_PATH}",
                headers=_billing_headers(supabase_key),
                timeout=2.0,
            )
    except httpx.TimeoutException:
        return False, "timeout"
    except httpx.HTTPError:
        return False, "connection_error"
    except Exception:
        return False, "connection_error"

    if response.status_code != 200:
        return False, "connection_error"

    try:
        payload = response.json()
    except ValueError:
        return False, "connection_error"

    if not isinstance(payload, list):
        return False, "connection_error"

    return True, "ok"


async def _probe_settlement_wallet_balance() -> dict:
    """Check the settlement wallet ETH balance on Base mainnet."""
    pk = os.environ.get("RHUMB_SETTLEMENT_PRIVATE_KEY", "").strip()
    if not pk:
        return {
            "settlement_wallet_configured": False,
            "settlement_wallet_eth_balance": "0",
            "settlement_wallet_eth_low": False,
            "settlement_wallet_eth_critical": False,
        }

    try:
        from eth_account import Account

        account = Account.from_key(pk)
        wallet_address = account.address
    except Exception:
        return {
            "settlement_wallet_configured": True,
            "settlement_wallet_eth_balance": "unknown",
            "settlement_wallet_eth_low": False,
            "settlement_wallet_eth_critical": False,
        }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                BASE_MAINNET_RPC,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getBalance",
                    "params": [wallet_address, "latest"],
                    "id": 1,
                },
            )
        result = resp.json().get("result")
        if result is None:
            raise RuntimeError("No result in RPC response")
        balance_wei = int(result, 16)
        balance_eth = balance_wei / 1e18
    except Exception as exc:
        logger.warning("Failed to check settlement wallet ETH balance: %s", exc)
        return {
            "settlement_wallet_configured": True,
            "settlement_wallet_eth_balance": "unknown",
            "settlement_wallet_eth_low": False,
            "settlement_wallet_eth_critical": False,
        }

    return {
        "settlement_wallet_configured": True,
        "settlement_wallet_eth_balance": f"{balance_eth:.6f}",
        "settlement_wallet_eth_low": balance_eth < 0.001,
        "settlement_wallet_eth_critical": balance_eth < 0.0005,
    }


async def check_billing_health() -> tuple[bool, str]:
    """Returns billing health for the live Supabase billing backend."""
    return await _probe_billing_health(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


async def get_payment_health(supabase_url: str, supabase_key: str) -> dict:
    """Return payment system health for the billing health endpoint."""
    billing_healthy, billing_reason = await _probe_billing_health(supabase_url, supabase_key)
    health = {
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
        "usdc_configured": bool(os.getenv("RHUMB_USDC_WALLET_ADDRESS")),
        "billing_table_accessible": billing_healthy,
        "billing_reason": billing_reason,
    }

    wallet_health = await _probe_settlement_wallet_balance()
    health.update(wallet_health)

    if billing_healthy:
        # Degrade if settlement wallet is configured but critically low on ETH
        if wallet_health.get("settlement_wallet_configured") and wallet_health.get("settlement_wallet_eth_critical"):
            health["status"] = "degraded"
        else:
            health["status"] = "operational"
    else:
        health["status"] = "degraded"

    return health
