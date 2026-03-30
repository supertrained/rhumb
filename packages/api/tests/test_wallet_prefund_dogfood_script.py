"""Tests for the wallet-prefund dogfood operator harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from services.x402_local_settlement import verify_authorization_signature

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "wallet_prefund_dogfood.py"

spec = importlib.util.spec_from_file_location("wallet_prefund_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
wallet_prefund_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wallet_prefund_dogfood)


@pytest.mark.anyio
async def test_build_signed_authorization_round_trips_with_local_verifier():
    private_key = "0x" + "ab" * 32
    authorization, signature = wallet_prefund_dogfood.build_signed_authorization(
        private_key=private_key,
        network="base",
        pay_to="0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
        amount_atomic="100000",
        validity_seconds=3600,
    )

    result = await verify_authorization_signature(authorization, signature)

    assert result["valid"] is True
    assert result["recovered_signer"].lower() == authorization["from"].lower()
    assert authorization["to"] == "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623"
    assert authorization["value"] == "100000"
    assert authorization["nonce"].startswith("0x")
