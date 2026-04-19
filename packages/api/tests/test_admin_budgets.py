from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_list_upstream_budgets_recanonicalizes_alias_backed_provider_rows(client):
    budgets = [
        {
            "provider": "brave-search",
            "used": 800,
            "limit": 1000,
            "percentage": 0.8,
            "status": "warning",
            "unit": "requests",
            "reset": "monthly",
            "durable": True,
            "reason": "",
        },
        {
            "provider": "brave-search-api",
            "used": 50,
            "limit": 1000,
            "percentage": 0.05,
            "status": "ok",
            "unit": "requests",
            "reset": "monthly",
            "durable": True,
            "reason": "",
        },
        {
            "provider": "pdl",
            "used": 960,
            "limit": 1000,
            "percentage": 0.96,
            "status": "critical",
            "unit": "requests",
            "reset": "monthly",
            "durable": True,
            "reason": "",
        },
        {
            "provider": "people-data-labs",
            "used": 40,
            "limit": 1000,
            "percentage": 0.04,
            "status": "ok",
            "unit": "requests",
            "reset": "monthly",
            "durable": True,
            "reason": "",
        },
    ]

    with patch(
        "routes.admin_budgets.get_all_provider_budgets",
        new=AsyncMock(return_value=budgets),
    ):
        resp = client.get("/v1/admin/upstream-budgets")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == [
        {
            "provider": "brave-search-api",
            "used": 850,
            "limit": 1000,
            "percentage": 0.85,
            "status": "warning",
            "unit": "requests",
            "reset": "monthly",
            "durable": True,
            "reason": "",
        },
        {
            "provider": "people-data-labs",
            "used": 1000,
            "limit": 1000,
            "percentage": 1.0,
            "status": "exhausted",
            "unit": "requests",
            "reset": "monthly",
            "durable": True,
            "reason": "",
        },
    ]
    assert body["summary"] == {
        "total_providers": 2,
        "exhausted": 1,
        "critical": 0,
        "warning": 1,
        "exhausted_providers": ["people-data-labs"],
        "critical_providers": [],
    }


def test_get_provider_budget_accepts_canonical_public_provider_id_and_publicizes_response(client):
    with patch(
        "routes.admin_budgets.get_provider_usage",
        new=AsyncMock(
            return_value={
                "provider": "brave-search",
                "used": 42,
                "limit": 2000,
                "percentage": 0.021,
                "status": "ok",
                "unit": "requests",
                "reset": "monthly",
                "durable": True,
                "reason": "",
            }
        ),
    ) as mock_get_provider_usage:
        resp = client.get("/v1/admin/upstream-budgets/brave-search-api")

    assert resp.status_code == 200
    mock_get_provider_usage.assert_awaited_once_with("brave-search")
    assert resp.json()["data"] == {
        "provider": "brave-search-api",
        "used": 42,
        "limit": 2000,
        "percentage": 0.021,
        "status": "ok",
        "unit": "requests",
        "reset": "monthly",
        "durable": True,
        "reason": "",
    }
