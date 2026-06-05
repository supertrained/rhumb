from __future__ import annotations

import pytest

from services.route_plan_state import RoutePlanStateStore, RoutePlanStateUnavailable


class MockQueryResult:
    def __init__(self, data=None):
        self.data = data


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data
        self.inserted = None

    def select(self, *args):
        return self

    def eq(self, *args):
        return self

    def lt(self, *args):
        return self

    def maybe_single(self):
        return self

    def delete(self):
        return self

    def insert(self, data):
        self.inserted = data
        return self

    def upsert(self, data):
        self.inserted = data
        return self

    async def execute(self):
        return MockQueryResult(self._data)


class MockSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.get(name, MockQueryBuilder())

    def set_table(self, name, builder):
        self._tables[name] = builder


@pytest.mark.asyncio
async def test_route_plan_state_first_claim_allowed_and_hashes_nonce() -> None:
    builder = MockQueryBuilder(None)
    db = MockSupabase()
    db.set_table("route_plan_state", builder)
    store = RoutePlanStateStore(db, cleanup_interval_seconds=99999)

    claim = await store.check_and_claim(
        nonce="nonce-001",
        route_plan_id_hash="sha256:plan",
        expires_at=1_800_000_300,
    )

    assert claim.allowed is True
    assert claim.state_backend == "database"
    assert claim.nonce_hash.startswith("sha256:")
    assert builder.inserted["nonce_hash"] == claim.nonce_hash
    assert builder.inserted["route_plan_id_hash"] == "sha256:plan"
    assert builder.inserted["state"] == "claimed"


@pytest.mark.asyncio
async def test_route_plan_state_existing_claim_is_replay() -> None:
    db = MockSupabase()
    db.set_table("route_plan_state", MockQueryBuilder({"state": "claimed"}))
    store = RoutePlanStateStore(db, cleanup_interval_seconds=99999)

    claim = await store.check_and_claim(
        nonce="nonce-001",
        route_plan_id_hash="sha256:plan",
        expires_at=1_800_000_300,
    )

    assert claim.allowed is False
    assert claim.stop_condition == "route_plan_replay"


@pytest.mark.asyncio
async def test_route_plan_state_existing_revoked_row_is_revoked() -> None:
    db = MockSupabase()
    db.set_table(
        "route_plan_state",
        MockQueryBuilder(
            {
                "state": "revoked",
                "revoked_at": "2026-06-04T00:00:00Z",
                "revocation_reason": "operator",
            }
        ),
    )
    store = RoutePlanStateStore(db, cleanup_interval_seconds=99999)

    claim = await store.check_and_claim(
        nonce="nonce-001",
        route_plan_id_hash="sha256:plan",
        expires_at=1_800_000_300,
    )

    assert claim.allowed is False
    assert claim.stop_condition == "route_plan_revoked"
    assert "operator" in claim.detail


@pytest.mark.asyncio
async def test_route_plan_state_db_failure_can_fail_closed() -> None:
    class FailingBuilder(MockQueryBuilder):
        async def execute(self):
            raise ConnectionError("db down")

    db = MockSupabase()
    db.set_table("route_plan_state", FailingBuilder())
    store = RoutePlanStateStore(db, cleanup_interval_seconds=99999)

    with pytest.raises(RoutePlanStateUnavailable):
        await store.check_and_claim(
            nonce="nonce-001",
            route_plan_id_hash="sha256:plan",
            expires_at=1_800_000_300,
            allow_fallback=False,
        )


@pytest.mark.asyncio
async def test_route_plan_state_memory_fallback_detects_replay() -> None:
    class FailingBuilder(MockQueryBuilder):
        async def execute(self):
            raise ConnectionError("db down")

    db = MockSupabase()
    db.set_table("route_plan_state", FailingBuilder())
    store = RoutePlanStateStore(db, cleanup_interval_seconds=99999)

    first = await store.check_and_claim(
        nonce="nonce-001",
        route_plan_id_hash="sha256:plan",
        expires_at=1_800_000_300,
    )
    second = await store.check_and_claim(
        nonce="nonce-001",
        route_plan_id_hash="sha256:plan",
        expires_at=1_800_000_300,
    )

    assert first.allowed is True
    assert first.state_backend == "memory_fallback"
    assert second.allowed is False
    assert second.stop_condition == "route_plan_replay"
