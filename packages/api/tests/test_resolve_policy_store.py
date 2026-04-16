from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.resolve_policy_store import ResolvePolicyStore


@pytest.mark.asyncio
async def test_get_policy_canonicalizes_legacy_runtime_alias_rows() -> None:
    store = ResolvePolicyStore()

    with patch(
        "services.resolve_policy_store.supabase_fetch",
        new=AsyncMock(
            return_value=[
                {
                    "org_id": "org_v2_test",
                    "pin": "brave-search",
                    "provider_preference": ["brave-search", "pdl", "brave-search-api"],
                    "provider_deny": ["pdl"],
                    "allow_only": ["brave-search"],
                    "max_cost_usd": 0.02,
                    "created_at": "2026-03-31T07:00:00Z",
                    "updated_at": "2026-03-31T07:05:00Z",
                }
            ]
        ),
    ):
        policy = await store.get_policy("org_v2_test")

    assert policy is not None
    assert policy.pin == "brave-search-api"
    assert policy.provider_preference == ["brave-search-api", "people-data-labs"]
    assert policy.provider_deny == ["people-data-labs"]
    assert policy.allow_only == ["brave-search-api"]
    assert policy.max_cost_usd == 0.02
    assert policy.updated_at == "2026-03-31T07:05:00Z"


@pytest.mark.asyncio
async def test_put_policy_canonicalizes_alias_inputs_before_persisting() -> None:
    store = ResolvePolicyStore()

    with (
        patch("services.resolve_policy_store.supabase_fetch", new=AsyncMock(return_value=[])),
        patch(
            "services.resolve_policy_store.supabase_insert_returning",
            new=AsyncMock(
                return_value={
                    "org_id": "org_v2_test",
                    "pin": "brave-search-api",
                    "provider_preference": ["brave-search-api", "people-data-labs"],
                    "provider_deny": ["people-data-labs"],
                    "allow_only": ["brave-search-api"],
                    "max_cost_usd": 0.02,
                    "created_at": "2026-03-31T07:00:00Z",
                    "updated_at": "2026-03-31T07:05:00Z",
                }
            ),
        ) as mock_insert,
    ):
        policy = await store.put_policy(
            "org_v2_test",
            pin="brave-search",
            provider_preference=["brave-search", "pdl", "brave-search-api"],
            provider_deny=["pdl"],
            allow_only=["brave-search"],
            max_cost_usd=0.02,
        )

    assert policy is not None
    assert mock_insert.await_args.args[0] == "resolve_account_policies"
    assert mock_insert.await_args.args[1] == {
        "org_id": "org_v2_test",
        "pin": "brave-search-api",
        "provider_preference": ["brave-search-api", "people-data-labs"],
        "provider_deny": ["people-data-labs"],
        "allow_only": ["brave-search-api"],
        "max_cost_usd": 0.02,
        "updated_at": mock_insert.await_args.args[1]["updated_at"],
    }
    assert policy.pin == "brave-search-api"
    assert policy.provider_preference == ["brave-search-api", "people-data-labs"]
    assert policy.provider_deny == ["people-data-labs"]
    assert policy.allow_only == ["brave-search-api"]
