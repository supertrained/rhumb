"""Payment request management for x402 USDC payments."""

import os
import logging
from typing import Optional
from datetime import datetime, timezone

import httpx
from config import settings

logger = logging.getLogger(__name__)

# USDC contract addresses (Base chain) — shared with x402.py
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


class PaymentRequestService:
    """Create and track x402 payment requests."""

    def _get_headers(self) -> dict[str, str]:
        return {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _get_wallet_address(self) -> str:
        """Get configured receive wallet address."""
        addr = os.environ.get("RHUMB_USDC_WALLET_ADDRESS", "")
        if not addr:
            raise ValueError("RHUMB_USDC_WALLET_ADDRESS not configured")
        return addr

    def _get_network_config(self) -> tuple[str, str]:
        """Return (network, usdc_contract) based on environment."""
        is_production = os.environ.get("RAILWAY_ENVIRONMENT", "") == "production"
        if is_production:
            return "base", USDC_BASE_MAINNET
        return "base-sepolia", USDC_BASE_SEPOLIA

    async def create_payment_request(
        self,
        org_id: Optional[str],
        capability_id: str,
        amount_usd_cents: int,
        execution_id: Optional[str] = None,
    ) -> dict:
        """Create a payment request and persist to DB.

        Returns the created payment_request row as dict.
        """
        wallet_address = self._get_wallet_address()
        network, usdc_contract = self._get_network_config()
        usdc_amount = str(amount_usd_cents * 10000)  # cents → atomic units

        payload = {
            "org_id": org_id,
            "capability_id": capability_id,
            "execution_id": execution_id,
            "amount_usdc_atomic": usdc_amount,
            "amount_usd_cents": amount_usd_cents,
            "network": network,
            "pay_to_address": wallet_address,
            "asset_address": usdc_contract,
            "status": "pending",
        }

        url = f"{settings.supabase_url}/rest/v1/payment_requests"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url, headers=self._get_headers(), json=payload, timeout=10.0,
                )
                if resp.status_code in (200, 201):
                    rows = resp.json()
                    return rows[0] if rows else payload
                logger.warning("Payment request insert failed: %s %s", resp.status_code, resp.text)
                return payload
        except Exception as e:
            logger.warning("Payment request creation failed: %s", e)
            return payload

    async def get_pending_request(self, payment_request_id: str) -> Optional[dict]:
        """Fetch a pending payment request by ID."""
        url = (
            f"{settings.supabase_url}/rest/v1/payment_requests"
            f"?id=eq.{payment_request_id}&status=eq.pending&select=*&limit=1"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._get_headers(), timeout=10.0)
                if resp.status_code == 200 and resp.json():
                    return resp.json()[0]
        except Exception as e:
            logger.warning("Payment request fetch failed: %s", e)
        return None

    async def mark_verified(self, payment_request_id: str, tx_hash: str) -> bool:
        """Mark a payment request as verified with a transaction hash."""
        url = f"{settings.supabase_url}/rest/v1/payment_requests?id=eq.{payment_request_id}"
        payload = {
            "status": "verified",
            "payment_tx_hash": tx_hash,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    url, headers=self._get_headers(), json=payload, timeout=10.0,
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning("Payment request verification update failed: %s", e)
            return False

    async def expire_stale_requests(self) -> int:
        """Expire pending requests past their deadline. Returns count expired."""
        now = datetime.now(timezone.utc).isoformat()
        url = (
            f"{settings.supabase_url}/rest/v1/payment_requests"
            f"?status=eq.pending&expires_at=lt.{now}"
        )
        payload = {"status": "expired"}
        headers = {**self._get_headers(), "Prefer": "return=headers-only,count=exact"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.patch(url, headers=headers, json=payload, timeout=10.0)
                # Parse count from Content-Range header
                cr = resp.headers.get("content-range", "")
                if "/" in cr:
                    total = cr.split("/")[-1]
                    return int(total) if total != "*" else 0
                return 0
        except Exception as e:
            logger.warning("Stale request expiry failed: %s", e)
            return 0
