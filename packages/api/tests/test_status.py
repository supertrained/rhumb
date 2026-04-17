from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import routes.status as status_route
from app import app


class _MockCredentialStore:
    def __init__(self, services: list[str]):
        self._services = services

    def callable_services(self) -> list[str]:
        return list(self._services)


@pytest.mark.anyio
async def test_check_proxy_canonicalizes_alias_backed_runtime_service_ids() -> None:
    store = _MockCredentialStore([
        "brave-search",
        "brave-search-api",
        "PDL",
        "people-data-labs",
    ])

    with patch("services.proxy_credentials.get_credential_store", return_value=store):
        payload = await status_route._check_proxy()

    assert payload["status"] == "operational"
    assert payload["details"]["callable_services"] == 2
    assert payload["details"]["services"] == [
        "brave-search-api",
        "people-data-labs",
    ]


@pytest.mark.anyio
async def test_status_endpoint_surfaces_canonical_proxy_service_ids() -> None:
    store = _MockCredentialStore(["brave-search", "pdl"])

    with (
        patch("services.proxy_credentials.get_credential_store", return_value=store),
        patch.object(status_route, "_check_supabase", new=AsyncMock(return_value={
            "component": "database",
            "status": "operational",
            "latency_ms": 1,
            "details": {},
        })),
        patch.object(status_route, "_check_payment", new=AsyncMock(return_value={
            "component": "payments",
            "status": "operational",
            "latency_ms": 1,
            "details": {},
        })),
        patch.object(status_route, "_check_billing", new=AsyncMock(return_value={
            "component": "billing",
            "status": "operational",
            "latency_ms": 1,
            "details": {},
        })),
        patch.object(status_route, "_check_scoring", new=AsyncMock(return_value={
            "component": "scoring",
            "status": "operational",
            "latency_ms": 1,
            "details": {},
        })),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/status")

    assert response.status_code == 200
    payload = response.json()
    proxy = next(component for component in payload["components"] if component["component"] == "proxy")
    assert proxy["details"]["callable_services"] == 2
    assert proxy["details"]["services"] == ["brave-search-api", "people-data-labs"]
