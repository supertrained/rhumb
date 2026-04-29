"""Tests for DB-read capability execution route (AUD-18 Wave 1)."""

from __future__ import annotations

import asyncio
from importlib import import_module
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.agent_identity import AgentIdentitySchema

FAKE_RHUMB_KEY = "rhumb_test_key_db_exec"


postgres_read_executor = import_module("services.postgres_read_executor")
db_connection_registry = import_module("services.db_connection_registry")
db_execute_route = import_module("routes.db_execute")


def _mock_agent() -> AgentIdentitySchema:
    return AgentIdentitySchema(
        agent_id="agent_db_test",
        name="db-test-agent",
        organization_id="org_db_test",
    )


@pytest.fixture
def app():
    return create_app()


@pytest.fixture(autouse=True)
def _mock_identity_store():
    mock_store = MagicMock()
    mock_store.verify_api_key_with_agent = AsyncMock(return_value=_mock_agent())
    with patch("routes.capability_execute._get_identity_store", return_value=mock_store):
        yield mock_store


@pytest.fixture(autouse=True)
def _mock_rate_limiter():
    mock_limiter = MagicMock()
    mock_limiter.check_and_increment = AsyncMock(return_value=(True, 29))
    with patch(
        "routes.capability_execute._get_rate_limiter",
        new_callable=AsyncMock,
        return_value=mock_limiter,
    ):
        yield mock_limiter


@pytest.fixture(autouse=True)
def _mock_kill_switch_registry():
    mock_registry = MagicMock()
    mock_registry.is_blocked.return_value = (False, None)
    with patch(
        "routes.capability_execute.init_kill_switch_registry",
        new_callable=AsyncMock,
        return_value=mock_registry,
    ):
        yield mock_registry


@pytest.fixture(autouse=True)
def _mock_billing_health():
    with patch(
        "routes.capability_execute.check_billing_health",
        new_callable=AsyncMock,
        return_value=(True, "ok"),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_supabase_writes():
    """Mock all Supabase writes for DB execute tests."""
    with patch.object(db_execute_route, "supabase_insert", new_callable=AsyncMock) as mock_insert:
        yield mock_insert


@pytest.fixture(autouse=True)
def _mock_receipt_service():
    """Mock the receipt service so we don't need a real chain state."""
    mock_receipt = MagicMock()
    mock_receipt.receipt_id = "rcpt_test_db_00000001"
    mock_receipt.receipt_hash = "sha256:abc123"
    mock_receipt.chain_sequence = 1

    mock_service = MagicMock()
    mock_service.create_receipt = AsyncMock(return_value=mock_receipt)

    with patch.object(db_execute_route, "get_receipt_service", return_value=mock_service):
        yield mock_service


class FakeCursor:
    def __init__(self, *, rows=None, description=None):
        self.rows = rows or []
        self.description = description or []
        self.executions: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=None):
        self.executions.append((sql, params))

    async def fetchmany(self, count):
        return list(self.rows[:count])

    async def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self, row_factory=None):
        return self._cursor

    async def close(self):
        pass


@asynccontextmanager
async def _fake_connect(dsn, **kwargs):
    cursor = FakeCursor(
        rows=[
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ],
        description=[
            SimpleNamespace(name="id", type_code="int4"),
            SimpleNamespace(name="name", type_code="text"),
        ],
    )
    conn = FakeConnection(cursor)
    yield conn
    await conn.close()


def _assert_failure_audit(
    mock_receipt_service,
    mock_supabase_writes,
    *,
    status_code: int,
    error_code: str,
    credential_mode: str,
    provider_used: str = "postgresql",
) -> None:
    mock_receipt_service.create_receipt.assert_called_once()
    receipt_input = mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.status == "failure"
    assert receipt_input.error_code == error_code
    assert receipt_input.provider_id == provider_used
    assert receipt_input.credential_mode == credential_mode

    assert mock_supabase_writes.await_count == 1
    table_name, payload = mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["upstream_status"] == status_code
    assert payload["success"] is False
    assert payload["credential_mode"] == credential_mode
    assert payload["provider_used"] == provider_used


@pytest.mark.asyncio
async def test_db_query_read_success(app, monkeypatch) -> None:
    """POST /v1/capabilities/db.query.read/execute returns query results."""
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "postgresql://localhost:5432/test")

    with patch.object(postgres_read_executor.psycopg.AsyncConnection, "connect") as mock_connect:
        cursor = FakeCursor(
            rows=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            description=[
                SimpleNamespace(name="id", type_code="int4"),
                SimpleNamespace(name="name", type_code="text"),
            ],
        )
        conn = FakeConnection(cursor)
        mock_connect.return_value = conn

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "connection_ref": "conn_reader",
                    "query": "SELECT id, name FROM users",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["capability_id"] == "db.query.read"
    assert body["data"]["connection_ref"] == "conn_reader"
    assert body["data"]["receipt_id"] == "rcpt_test_db_00000001"
    assert "summary" in body
    assert "via conn_reader" in body["summary"]
    assert "Read" in body["summary"]


@pytest.mark.asyncio
async def test_db_execute_rejects_missing_api_key(app) -> None:
    """DB execute requires X-Rhumb-Key (no x402 anonymous)."""
    # Override the mock to return None for missing key
    with patch("routes.capability_execute._get_identity_store") as mock_store_fn:
        mock_store = MagicMock()
        mock_store.verify_api_key_with_agent = AsyncMock(return_value=None)
        mock_store_fn.return_value = mock_store

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                json={
                    "connection_ref": "conn_reader",
                    "query": "SELECT 1",
                },
            )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_db_execute_rejects_invalid_connection_ref(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Invalid connection_ref returns 400 and still records provenance."""
    monkeypatch.delenv("RHUMB_DB_CONN_BAD", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_bad",
                "query": "SELECT 1",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_connection_ref_invalid"
    assert body["connection_ref"] == "conn_bad"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_connection_ref_invalid",
        credential_mode="byok",
    )


def test_db_execute_rejects_non_object_body_before_connection_reads(
    app,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json=["not", "an", "object"],
            )

    with (
        patch.object(db_execute_route, "validate_connection_ref") as mock_validate,
        patch.object(db_execute_route, "execute_read_query", new=AsyncMock()) as mock_execute,
    ):
        response = asyncio.run(_run())

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_request_invalid"
    assert body["message"] == "JSON body must be an object"
    mock_validate.assert_not_called()
    mock_execute.assert_not_called()
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_request_invalid",
        credential_mode="byok",
    )


@pytest.mark.asyncio
async def test_db_execute_rejects_disabled_connection_ref_placeholder(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Disabled env placeholders should fail as connection_ref errors, not SQL errors."""
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "disabled")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_reader",
                "query": "SELECT 1",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_connection_ref_invalid"
    assert body["connection_ref"] == "conn_reader"
    assert "disabled or invalid" in body["message"]
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_connection_ref_invalid",
        credential_mode="byok",
    )


@pytest.mark.asyncio
async def test_db_execute_agent_vault_requires_token_header(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """agent_vault DB execute requires X-Agent-Token header."""
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_reader",
                "credential_mode": "agent_vault",
                "query": "SELECT 1",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_agent_token_required"
    assert body["connection_ref"] == "conn_reader"
    assert "X-Agent-Token" in body["message"]
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_agent_token_required",
        credential_mode="agent_vault",
    )


@pytest.mark.asyncio
async def test_db_execute_rejects_invalid_agent_vault_dsn(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Invalid agent_vault DSNs fail with audited 400 provenance."""
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={
                "X-Rhumb-Key": FAKE_RHUMB_KEY,
                "X-Agent-Token": "not-a-dsn",
            },
            json={
                "connection_ref": "conn_reader",
                "credential_mode": "agent_vault",
                "query": "SELECT 1",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_agent_token_invalid"
    assert body["connection_ref"] == "conn_reader"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_agent_token_invalid",
        credential_mode="agent_vault",
    )


@pytest.mark.asyncio
async def test_db_query_read_success_agent_vault(app, monkeypatch) -> None:
    """agent_vault DB execute uses the DSN supplied in X-Agent-Token."""
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)
    token_dsn = "postgresql://reader:pass@localhost:5432/test"

    with patch.object(postgres_read_executor.psycopg.AsyncConnection, "connect") as mock_connect:
        cursor = FakeCursor(
            rows=[{"count": 1}],
            description=[SimpleNamespace(name="count", type_code="int8")],
        )
        conn = FakeConnection(cursor)
        mock_connect.return_value = conn

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": token_dsn,
                },
                json={
                    "connection_ref": "conn_reader",
                    "credential_mode": "agent_vault",
                    "query": "SELECT 1",
                },
            )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["credential_mode"] == "agent_vault"
    assert body["connection_ref"] == "conn_reader"
    assert body["rows"] == [{"count": 1}]
    assert mock_connect.call_args[0][0] == token_dsn


@pytest.mark.asyncio
async def test_db_query_read_success_agent_vault_signed_token(app, monkeypatch) -> None:
    """Signed DB agent_vault tokens resolve to the bound PostgreSQL DSN."""
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)
    token_dsn = "postgresql://reader:pass@localhost:5432/test"
    signed_token = db_connection_registry.issue_agent_vault_dsn_token(
        token_dsn,
        connection_ref="conn_reader",
        agent_id="agent_db_test",
        org_id="org_db_test",
        issued_at=1_744_105_600,
        ttl_seconds=300,
        secret="test-db-vault-secret",
    )

    monkeypatch.setenv("RHUMB_DB_AGENT_VAULT_SECRET", "test-db-vault-secret")

    with patch.object(postgres_read_executor.psycopg.AsyncConnection, "connect") as mock_connect:
        cursor = FakeCursor(
            rows=[{"count": 1}],
            description=[SimpleNamespace(name="count", type_code="int8")],
        )
        conn = FakeConnection(cursor)
        mock_connect.return_value = conn

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": signed_token,
                },
                json={
                    "connection_ref": "conn_reader",
                    "credential_mode": "agent_vault",
                    "query": "SELECT 1",
                },
            )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["credential_mode"] == "agent_vault"
    assert body["connection_ref"] == "conn_reader"
    assert body["rows"] == [{"count": 1}]
    assert mock_connect.call_args[0][0] == token_dsn


@pytest.mark.asyncio
async def test_db_execute_rejects_signed_agent_vault_token_connection_ref_mismatch(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Signed DB agent_vault tokens must match the requested connection_ref."""
    monkeypatch.delenv("RHUMB_DB_CONN_READER", raising=False)
    signed_token = db_connection_registry.issue_agent_vault_dsn_token(
        "postgresql://reader:pass@localhost:5432/test",
        connection_ref="conn_primary",
        agent_id="agent_db_test",
        org_id="org_db_test",
        issued_at=1_744_105_600,
        ttl_seconds=300,
        secret="test-db-vault-secret",
    )

    monkeypatch.setenv("RHUMB_DB_AGENT_VAULT_SECRET", "test-db-vault-secret")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={
                "X-Rhumb-Key": FAKE_RHUMB_KEY,
                "X-Agent-Token": signed_token,
            },
            json={
                "connection_ref": "conn_reader",
                "credential_mode": "agent_vault",
                "query": "SELECT 1",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_agent_token_invalid"
    assert body["connection_ref"] == "conn_reader"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_agent_token_invalid",
        credential_mode="agent_vault",
    )


@pytest.mark.asyncio
async def test_db_execute_validation_error_emits_failure_receipt_and_execution_row(
    app,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Pydantic validation errors are audited with a 422 execution status."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={"connection_ref": "conn_reader"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "db_request_validation_error"
    assert body["connection_ref"] == "conn_reader"
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=422,
        error_code="db_request_validation_error",
        credential_mode="byok",
    )


@pytest.mark.asyncio
async def test_db_execute_invalid_json_emits_failure_receipt_and_execution_row(
    app,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Invalid JSON bodies are audited with the actual 400 status."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={
                "X-Rhumb-Key": FAKE_RHUMB_KEY,
                "Content-Type": "application/json",
            },
            content="{",
        )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "db_request_invalid"
    assert "connection_ref" not in body
    _assert_failure_audit(
        _mock_receipt_service,
        _mock_supabase_writes,
        status_code=400,
        error_code="db_request_invalid",
        credential_mode="byok",
    )


@pytest.mark.asyncio
async def test_db_query_read_supabase_dsn_uses_supabase_provider(
    app,
    monkeypatch,
    _mock_receipt_service,
    _mock_supabase_writes,
) -> None:
    """Supabase-backed Postgres DSNs are attributed as supabase end to end."""
    monkeypatch.setenv(
        "RHUMB_DB_CONN_READER",
        "postgresql://postgres:pass@db.abcdefghijklmnop.supabase.co:5432/postgres",
    )

    with patch.object(postgres_read_executor.psycopg.AsyncConnection, "connect") as mock_connect:
        cursor = FakeCursor(
            rows=[{"count": 1}],
            description=[SimpleNamespace(name="count", type_code="int8")],
        )
        mock_connect.return_value = FakeConnection(cursor)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "connection_ref": "conn_reader",
                    "query": "SELECT 1 as count",
                },
            )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["provider_used"] == "supabase"
    assert body["connection_ref"] == "conn_reader"

    receipt_input = _mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.provider_id == "supabase"

    assert _mock_supabase_writes.await_count == 1
    table_name, payload = _mock_supabase_writes.await_args.args
    assert table_name == "capability_executions"
    assert payload["provider_used"] == "supabase"


@pytest.mark.asyncio
async def test_db_execute_rejects_write_query(app, monkeypatch) -> None:
    """Write queries are blocked by the classifier."""
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "postgresql://localhost:5432/test")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_reader",
                "query": "DELETE FROM users WHERE id = 1",
            },
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "db_query_not_read_only"
    assert body["connection_ref"] == "conn_reader"


@pytest.mark.asyncio
async def test_db_execute_emits_receipt_on_success(app, monkeypatch, _mock_receipt_service) -> None:
    """Successful DB execution emits a chain-hashed receipt."""
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "postgresql://localhost:5432/test")

    with patch.object(postgres_read_executor.psycopg.AsyncConnection, "connect") as mock_connect:
        cursor = FakeCursor(
            rows=[{"count": 42}],
            description=[SimpleNamespace(name="count", type_code="int8")],
        )
        mock_connect.return_value = FakeConnection(cursor)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
                json={
                    "connection_ref": "conn_reader",
                    "query": "SELECT count(*) as count FROM users",
                },
            )

    assert response.status_code == 200
    _mock_receipt_service.create_receipt.assert_called_once()
    receipt_input = _mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.capability_id == "db.query.read"
    assert receipt_input.provider_id == "postgresql"
    assert receipt_input.status == "success"


@pytest.mark.asyncio
async def test_db_execute_emits_receipt_on_failure(app, monkeypatch, _mock_receipt_service) -> None:
    """Failed DB execution (write attempt) still emits a failure receipt."""
    monkeypatch.setenv("RHUMB_DB_CONN_READER", "postgresql://localhost:5432/test")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_reader",
                "query": "INSERT INTO users (name) VALUES ('evil')",
            },
        )

    assert response.status_code == 422
    _mock_receipt_service.create_receipt.assert_called_once()
    receipt_input = _mock_receipt_service.create_receipt.call_args[0][0]
    assert receipt_input.status == "failure"
    assert receipt_input.error_code is not None


def test_db_agent_vault_tokenize_rejects_blank_key_before_identity_store(
    app,
    _mock_identity_store,
) -> None:
    """Blank governed keys reject before identity-store verification."""
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/db/agent-vault/tokenize",
            headers={"X-Rhumb-Key": "   "},
            json={
                "connection_ref": "conn_reader",
                "dsn": "postgresql://reader:pass@localhost:5432/app",
                "ttl_seconds": 300,
            },
        )
    finally:
        client.close()

    assert response.status_code == 401
    assert response.json()["detail"] == "X-Rhumb-Key header required"
    _mock_identity_store.verify_api_key_with_agent.assert_not_awaited()


def test_db_direct_execute_rejects_blank_key_before_identity_store(
    app,
    _mock_identity_store,
) -> None:
    """Direct execute treats whitespace X-Rhumb-Key as missing before state reads."""
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/capabilities/db.query.read/execute",
            headers={"X-Rhumb-Key": "   "},
            json={
                "connection_ref": "conn_reader",
                "query": "SELECT 1",
            },
        )
    finally:
        client.close()

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "authentication_required"
    assert "X-Rhumb-Key" in body["message"]
    _mock_identity_store.verify_api_key_with_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_db_agent_vault_tokenize_route_returns_signed_token(app, monkeypatch) -> None:
    """Authenticated callers can exchange a raw DSN for a signed DB vault token."""
    monkeypatch.setenv("RHUMB_DB_AGENT_VAULT_SECRET", "test-db-agent-vault-secret")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/db/agent-vault/tokenize",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_reader",
                "dsn": "postgresql://reader:pass@localhost:5432/app",
                "ttl_seconds": 300,
            },
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["token"].startswith("rhdbv1.")
    assert body["token_format"] == "rhdbv1"
    assert body["connection_ref"] == "conn_reader"
    assert "postgresql://reader:pass@localhost:5432/app" not in body["token"]


@pytest.mark.asyncio
async def test_db_query_read_success_with_tokenized_agent_vault(app, monkeypatch) -> None:
    """DB execute accepts the signed DB vault token returned by the tokenize route."""
    monkeypatch.setenv("RHUMB_DB_AGENT_VAULT_SECRET", "test-db-agent-vault-secret")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        tokenize_response = await client.post(
            "/v1/db/agent-vault/tokenize",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={
                "connection_ref": "conn_reader",
                "dsn": "postgresql://reader:pass@localhost:5432/test",
                "ttl_seconds": 300,
            },
        )

    signed_token = tokenize_response.json()["data"]["token"]

    with patch.object(postgres_read_executor.psycopg.AsyncConnection, "connect") as mock_connect:
        cursor = FakeCursor(
            rows=[{"count": 1}],
            description=[SimpleNamespace(name="count", type_code="int8")],
        )
        conn = FakeConnection(cursor)
        mock_connect.return_value = conn

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/capabilities/db.query.read/execute",
                headers={
                    "X-Rhumb-Key": FAKE_RHUMB_KEY,
                    "X-Agent-Token": signed_token,
                },
                json={
                    "connection_ref": "conn_reader",
                    "credential_mode": "agent_vault",
                    "query": "SELECT 1",
                },
            )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["credential_mode"] == "agent_vault"
    assert body["connection_ref"] == "conn_reader"
    assert body["rows"] == [{"count": 1}]
    assert mock_connect.call_args[0][0] == "postgresql://reader:pass@localhost:5432/test"


@pytest.mark.asyncio
async def test_non_db_capability_falls_through(app) -> None:
    """Non-DB capability IDs should NOT be handled by the DB execute path."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # email.send should fall through to the main execute route
        response = await client.post(
            "/v1/capabilities/email.send/execute",
            headers={"X-Rhumb-Key": FAKE_RHUMB_KEY},
            json={"body": {"to": "test@example.com"}},
        )

    # The main route will handle this and likely return a provider-related error,
    # but crucially it should NOT be a db_* error code.
    body = response.json()
    error = body.get("error", "")
    assert not error.startswith("db_")
