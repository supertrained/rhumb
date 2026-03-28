"""Integration tests for DF-19 wallet spend-from-balance execution."""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from httpx import ASGITransport, AsyncClient

from app import create_app
from middleware.rate_limit import _buckets as _rate_limit_buckets
from routes import capability_execute as capability_execute_route
from schemas.agent_identity import reset_identity_store
from services.budget_enforcer import BudgetCheckResult
from services.credit_deduction import CreditDeductionResult, CreditReleaseResult
from services.wallet_auth import reset_challenge_throttle


TEST_PRIVATE_KEY = "0x" + "ab" * 32
TEST_ACCOUNT = Account.from_key(TEST_PRIVATE_KEY)
TEST_ADDRESS = TEST_ACCOUNT.address
TOPUP_AMOUNT_CENTS = 50
EXECUTION_COST_USD = 0.10
EXECUTION_BILLED_CENTS = 12
EXPECTED_REMAINING_CENTS = TOPUP_AMOUNT_CENTS - EXECUTION_BILLED_CENTS


@dataclass
class WalletBootstrapResult:
    wallet_session_token: str
    api_key: str
    org_id: str
    agent_id: str
    payment_request_id: str


class InMemorySupabase:
    """Tiny in-memory table store for route-level integration tests."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {
            "capabilities": [
                {
                    "id": "email.send",
                    "domain": "email",
                    "action": "send",
                    "description": "Send an email",
                }
            ],
            "capability_services": [
                {
                    "capability_id": "email.send",
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /emails",
                    "cost_per_call": EXECUTION_COST_USD,
                    "cost_currency": "USD",
                    "free_tier_calls": 0,
                }
            ],
            "services": [{"slug": "resend", "api_domain": "api.resend.com"}],
            "wallet_auth_challenges": [],
            "wallet_identities": [],
            "orgs": [],
            "org_credits": [],
            "wallet_balance_topups": [],
            "usdc_receipts": [],
            "credit_ledger": [],
            "capability_executions": [],
        }
        self._counter = 0

    def _next_id(self, table: str) -> str:
        self._counter += 1
        prefix = {
            "wallet_auth_challenges": "challenge",
            "wallet_identities": "wallet",
            "wallet_balance_topups": "topup",
            "usdc_receipts": "receipt",
            "credit_ledger": "ledger",
            "capability_executions": "exec",
            "orgs": "org",
            "org_credits": "credits",
        }.get(table, table)
        return f"{prefix}_{self._counter:04d}"

    def _match(self, row: dict, query: dict[str, list[str]]) -> bool:
        for key, values in query.items():
            if key in {"select", "limit", "order"}:
                continue
            value = values[-1]
            if value == "is.null":
                if row.get(key) is not None:
                    return False
                continue
            if value.startswith("eq."):
                expected = unquote(value[3:])
                if str(row.get(key)) != expected:
                    return False
        return True

    async def fetch(self, path: str) -> list[dict]:
        table, _, query_string = path.partition("?")
        query = parse_qs(query_string, keep_blank_values=True)
        rows = [deepcopy(row) for row in self.tables.get(table, []) if self._match(row, query)]

        order = query.get("order", [None])[-1]
        if order:
            field, _, direction = order.partition(".")
            rows.sort(key=lambda row: row.get(field) or "", reverse=direction == "desc")

        limit = query.get("limit", [None])[-1]
        if limit is not None:
            rows = rows[: int(limit)]
        return rows

    async def insert(self, table: str, payload: dict) -> bool:
        await self.insert_returning(table, payload)
        return True

    async def insert_returning(self, table: str, payload: dict) -> dict:
        row = deepcopy(payload)
        row.setdefault("id", self._next_id(table))
        row.setdefault("created_at", datetime.now(tz=UTC).isoformat())
        self.tables.setdefault(table, []).append(row)
        return deepcopy(row)

    async def patch(self, path: str, payload: dict) -> list[dict]:
        table, _, query_string = path.partition("?")
        query = parse_qs(query_string, keep_blank_values=True)
        updated: list[dict] = []
        for row in self.tables.get(table, []):
            if self._match(row, query):
                row.update(deepcopy(payload))
                updated.append(deepcopy(row))
        return updated

    def get_single(self, table: str, **filters: str) -> dict | None:
        for row in self.tables.get(table, []):
            if all(str(row.get(key)) == value for key, value in filters.items()):
                return row
        return None


class InMemoryPaymentRequests:
    def __init__(self) -> None:
        self._requests: dict[str, dict] = {}
        self._counter = 0

    async def create_payment_request(
        self,
        org_id: str | None,
        capability_id: str | None,
        amount_usd_cents: int,
        execution_id: str | None = None,
        *,
        purpose: str = "execution",
    ) -> dict:
        self._counter += 1
        request_id = f"pr_{self._counter:04d}"
        row = {
            "id": request_id,
            "org_id": org_id,
            "capability_id": capability_id,
            "execution_id": execution_id,
            "amount_usd_cents": amount_usd_cents,
            "amount_usdc_atomic": str(amount_usd_cents * 10000),
            "network": "base",
            "pay_to_address": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
            "asset_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "purpose": purpose,
            "status": "pending",
        }
        self._requests[request_id] = row
        return deepcopy(row)

    async def get_pending_request(self, payment_request_id: str) -> dict | None:
        row = self._requests.get(payment_request_id)
        if row and row.get("status") == "pending":
            return deepcopy(row)
        return None

    async def mark_verified(self, payment_request_id: str, tx_hash: str) -> bool:
        row = self._requests.get(payment_request_id)
        if row is None:
            return False
        row["status"] = "verified"
        row["payment_tx_hash"] = tx_hash
        return True


class InMemoryCreditDeduction:
    def __init__(self, db: InMemorySupabase) -> None:
        self._db = db
        self.deduct_calls: list[dict] = []

    async def deduct(self, org_id: str, amount_cents: int, **kwargs) -> CreditDeductionResult:
        row = self._db.get_single("org_credits", org_id=org_id)
        current_balance = int(row["balance_usd_cents"]) if row else 0
        self.deduct_calls.append(
            {
                "org_id": org_id,
                "amount_cents": amount_cents,
                "execution_id": kwargs.get("execution_id"),
            }
        )

        if row is None:
            return CreditDeductionResult(
                allowed=False,
                remaining_cents=None,
                reason="no_org_credits",
            )
        if current_balance < amount_cents:
            return CreditDeductionResult(
                allowed=False,
                remaining_cents=current_balance,
                reason="insufficient_credits",
            )

        row["balance_usd_cents"] = current_balance - amount_cents
        return CreditDeductionResult(
            allowed=True,
            remaining_cents=row["balance_usd_cents"],
            ledger_id=f"ledger_exec_{len(self.deduct_calls):04d}",
        )

    async def release(self, org_id: str, amount_cents: int, **kwargs) -> CreditReleaseResult:
        row = self._db.get_single("org_credits", org_id=org_id)
        if row is not None:
            row["balance_usd_cents"] = int(row["balance_usd_cents"]) + amount_cents
        return CreditReleaseResult(
            released=True,
            remaining_cents=row["balance_usd_cents"] if row else None,
            ledger_id=f"ledger_release_{kwargs.get('execution_id', 'unknown')}",
        )


def _sign_message(message: str) -> str:
    signed = Account.sign_message(encode_defunct(text=message), private_key=TEST_PRIVATE_KEY)
    return signed.signature.hex()


def _reset_all() -> None:
    reset_challenge_throttle()
    _rate_limit_buckets.clear()
    reset_identity_store()
    capability_execute_route._identity_store = None
    capability_execute_route._wallet_requests.clear()
    capability_execute_route._used_tx_hashes.clear()
    capability_execute_route._agent_exec_requests.clear()
    capability_execute_route._agent_managed_daily.clear()


async def _bootstrap_prefunded_wallet(
    client: AsyncClient,
) -> WalletBootstrapResult:
    challenge_resp = await client.post(
        "/v1/auth/wallet/request-challenge",
        json={"chain": "base", "address": TEST_ADDRESS, "purpose": "access"},
    )
    assert challenge_resp.status_code == 200
    challenge_data = challenge_resp.json()["data"]

    verify_resp = await client.post(
        "/v1/auth/wallet/verify",
        json={
            "challenge_id": challenge_data["challenge_id"],
            "signature": _sign_message(challenge_data["message"]),
        },
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()["data"]

    wallet_session_token = verify_data["wallet_session_token"]
    auth_header = {"Authorization": f"Bearer {wallet_session_token}"}

    topup_request_resp = await client.post(
        "/v1/auth/wallet/topup/request",
        json={"amount_usd_cents": TOPUP_AMOUNT_CENTS},
        headers=auth_header,
    )
    assert topup_request_resp.status_code == 200
    topup_request_data = topup_request_resp.json()["data"]

    topup_verify_resp = await client.post(
        "/v1/auth/wallet/topup/verify",
        json={
            "payment_request_id": topup_request_data["payment_request_id"],
            "x_payment": {
                "payload": {
                    "authorization": {
                        "from": TEST_ADDRESS,
                        "to": "0xEA63eF9B4FaC31DB058977065C8Fe12fdCa02623",
                        "value": str(TOPUP_AMOUNT_CENTS * 10000),
                    },
                    "signature": "0x" + "ab" * 65,
                }
            },
        },
        headers=auth_header,
    )
    assert topup_verify_resp.status_code == 200

    return WalletBootstrapResult(
        wallet_session_token=wallet_session_token,
        api_key=verify_data["api_key"],
        org_id=verify_data["wallet"]["org_id"],
        agent_id=verify_data["wallet"]["agent_id"],
        payment_request_id=topup_request_data["payment_request_id"],
    )


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def wallet_env():
    _reset_all()

    db = InMemorySupabase()
    payment_requests = InMemoryPaymentRequests()
    credit_deduction = InMemoryCreditDeduction(db)

    budget = MagicMock()
    budget.check_and_decrement = AsyncMock(
        return_value=BudgetCheckResult(allowed=True, remaining_usd=None)
    )
    budget.release = AsyncMock()

    settlement = MagicMock()
    settlement.verify_and_settle = AsyncMock(
        return_value={
            "verify": {"isValid": True, "payer": TEST_ADDRESS},
            "settle": {"success": True, "transaction": "0x" + "cd" * 32},
            "payer": TEST_ADDRESS,
            "transaction": "0x" + "cd" * 32,
            "network": "base",
        }
    )

    upstream_response = MagicMock()
    upstream_response.status_code = 200
    upstream_response.headers = {"content-type": "application/json"}
    upstream_response.json.return_value = {"id": "msg_123", "status": "sent"}
    upstream_response.text = '{"id":"msg_123","status":"sent"}'
    upstream_response.content = b'{"id":"msg_123","status":"sent"}'

    pool_client = MagicMock()
    pool_client.request = AsyncMock(return_value=upstream_response)

    httpx_client = MagicMock()
    httpx_client.request = AsyncMock(return_value=upstream_response)
    httpx_client.__aenter__ = AsyncMock(return_value=httpx_client)
    httpx_client.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = AsyncMock(return_value=pool_client)
    pool.release = AsyncMock()

    breaker = MagicMock()
    breaker.allow_request.return_value = True
    breaker.record_success.return_value = None
    breaker.record_failure.return_value = None

    breaker_registry = MagicMock()
    breaker_registry.get.return_value = breaker

    async def _bootstrap_org(org_id: str, **kwargs) -> dict:
        if db.get_single("orgs", id=org_id) is None:
            await db.insert("orgs", {"id": org_id, "name": kwargs.get("name") or org_id, "tier": "free"})
        if db.get_single("org_credits", org_id=org_id) is None:
            await db.insert("org_credits", {"org_id": org_id, "balance_usd_cents": 0})
        return {"org_created": True, "wallet_created": True, "seeded_credits_cents": 0}

    patches = ExitStack()
    for module_path in ("routes.auth_wallet", "routes.wallet_topup", "routes.capability_execute"):
        patches.enter_context(patch(f"{module_path}.supabase_fetch", new=AsyncMock(side_effect=db.fetch)))
        patches.enter_context(patch(f"{module_path}.supabase_insert", new=AsyncMock(side_effect=db.insert)))
        patches.enter_context(patch(f"{module_path}.supabase_patch", new=AsyncMock(side_effect=db.patch)))

    for module_path in ("routes.auth_wallet", "routes.wallet_topup"):
        patches.enter_context(
            patch(f"{module_path}.supabase_insert_returning", new=AsyncMock(side_effect=db.insert_returning))
        )

    patches.enter_context(patch("routes.auth_wallet.ensure_org_billing_bootstrap", new=AsyncMock(side_effect=_bootstrap_org)))
    patches.enter_context(patch("routes.wallet_topup._payment_requests", payment_requests))
    patches.enter_context(patch("routes.wallet_topup._settlement", settlement))
    patches.enter_context(patch("routes.capability_execute._budget_enforcer", budget))
    patches.enter_context(patch("routes.capability_execute._credit_deduction", credit_deduction))
    patches.enter_context(
        patch("routes.capability_execute.check_billing_health", new=AsyncMock(return_value=(True, "ok")))
    )
    patches.enter_context(
        patch("routes.capability_execute.check_and_trigger_auto_reload", new=AsyncMock(return_value=None))
    )
    patches.enter_context(
        patch("routes.capability_execute._inject_auth_headers", side_effect=lambda slug, auth, headers: headers)
    )
    patches.enter_context(patch("routes.capability_execute.get_pool_manager", return_value=pool))
    patches.enter_context(patch("routes.capability_execute.get_breaker_registry", return_value=breaker_registry))
    patches.enter_context(patch("routes.capability_execute.httpx.AsyncClient", return_value=httpx_client))

    try:
        yield SimpleNamespace(
            db=db,
            payment_requests=payment_requests,
            credit_deduction=credit_deduction,
            budget=budget,
            pool=pool,
        )
    finally:
        patches.close()


@pytest.mark.asyncio
async def test_wallet_prefund_then_execute_via_api_key_uses_org_credits(app, wallet_env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        wallet = await _bootstrap_prefunded_wallet(client)

        execute_resp = await client.post(
            "/v1/capabilities/email.send/execute",
            json={
                "provider": "resend",
                "credential_mode": "byo",
                "method": "POST",
                "path": "/emails",
                "body": {"to": "test@example.com", "subject": "Wallet test"},
            },
            headers={"X-Rhumb-Key": wallet.api_key},
        )

    assert execute_resp.status_code == 200
    body = execute_resp.json()["data"]
    assert body["org_credits_remaining_cents"] == EXPECTED_REMAINING_CENTS
    assert wallet_env.credit_deduction.deduct_calls == [
        {
            "org_id": wallet.org_id,
            "amount_cents": EXECUTION_BILLED_CENTS,
            "execution_id": body["execution_id"],
        }
    ]


@pytest.mark.asyncio
async def test_prefunded_wallet_execution_does_not_require_x_payment(app, wallet_env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        wallet = await _bootstrap_prefunded_wallet(client)

        execute_resp = await client.post(
            "/v1/capabilities/email.send/execute",
            json={
                "provider": "resend",
                "credential_mode": "byo",
                "method": "POST",
                "path": "/emails",
                "body": {"to": "test@example.com", "subject": "No x-payment"},
            },
            headers={"X-Rhumb-Key": wallet.api_key},
        )

    assert execute_resp.status_code == 200
    assert execute_resp.json()["error"] is None
    assert "X-Payment" not in execute_resp.headers


@pytest.mark.asyncio
async def test_prefunded_wallet_balance_decrements_after_execution(app, wallet_env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        wallet = await _bootstrap_prefunded_wallet(client)
        auth_header = {"Authorization": f"Bearer {wallet.wallet_session_token}"}

        balance_before_resp = await client.get("/v1/auth/wallet/balance", headers=auth_header)
        assert balance_before_resp.status_code == 200
        assert balance_before_resp.json()["data"]["balance_usd_cents"] == TOPUP_AMOUNT_CENTS

        execute_resp = await client.post(
            "/v1/capabilities/email.send/execute",
            json={
                "provider": "resend",
                "credential_mode": "byo",
                "method": "POST",
                "path": "/emails",
                "body": {"to": "test@example.com", "subject": "Balance check"},
            },
            headers={"X-Rhumb-Key": wallet.api_key},
        )
        assert execute_resp.status_code == 200

        balance_after_resp = await client.get("/v1/auth/wallet/balance", headers=auth_header)

    assert balance_after_resp.status_code == 200
    assert balance_after_resp.json()["data"]["balance_usd_cents"] == EXPECTED_REMAINING_CENTS
