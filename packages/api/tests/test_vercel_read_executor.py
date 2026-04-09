"""Tests for the Vercel deployment read-first executor."""

from __future__ import annotations

import pytest

from schemas.deployment_capabilities import DeploymentGetRequest, DeploymentListRequest
from services.deployment_connection_registry import VercelDeploymentBundle
from services.vercel_read_executor import (
    VercelExecutorError,
    _build_headers,
    get_deployment,
    list_deployments,
)


class MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class MockAsyncClient:
    def __init__(self, *, responses: dict[str, MockResponse], **_kwargs):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, path: str, params=None):
        response = self.responses.get(path)
        if response is None:
            raise AssertionError(f"unexpected path: {path} params={params}")
        return response


def _bundle(**overrides) -> VercelDeploymentBundle:
    data = {
        "deployment_ref": "dep_main",
        "provider": "vercel",
        "auth_mode": "bearer_token",
        "bearer_token": "token-123",
        "allowed_project_ids": ("prj_123",),
        "allowed_targets": ("production",),
        "team_id": "team_123",
    }
    data.update(overrides)
    return VercelDeploymentBundle(**data)


@pytest.mark.asyncio
async def test_list_deployments_filters_out_of_scope_items() -> None:
    request = DeploymentListRequest(deployment_ref="dep_main", limit=10)
    bundle = _bundle(allowed_targets=())
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/v6/deployments": MockResponse(
                200,
                {
                    "deployments": [
                        {
                            "uid": "dpl_1",
                            "name": "rhumb-api",
                            "projectId": "prj_123",
                            "target": "production",
                            "url": "rhumb-api.vercel.app",
                            "createdAt": 1712677200000,
                            "ready": 1712677260000,
                            "creator": {"uid": "user_1", "username": "pedro"},
                        },
                        {
                            "uid": "dpl_2",
                            "name": "other-app",
                            "projectId": "prj_999",
                            "target": "production",
                            "url": "other-app.vercel.app",
                        },
                    ],
                    "pagination": {"next": 1712600000000},
                },
            )
        }
    )

    response = await list_deployments(request, bundle=bundle, client_factory=client_factory)

    assert response.deployment_count_returned == 1
    assert response.deployments[0].deployment_id == "dpl_1"
    assert response.deployments[0].project_id == "prj_123"
    assert response.next_page_after == 1712600000000
    assert response.has_more is True


@pytest.mark.asyncio
async def test_list_deployments_rejects_out_of_scope_target_filter() -> None:
    request = DeploymentListRequest(deployment_ref="dep_main", target="preview")
    bundle = _bundle(allowed_targets=("production",))

    with pytest.raises(VercelExecutorError) as exc:
        await list_deployments(request, bundle=bundle, client_factory=lambda **kwargs: MockAsyncClient(responses={}))

    assert exc.value.code == "deployment_target_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_deployment_rejects_out_of_scope_project() -> None:
    request = DeploymentGetRequest(deployment_ref="dep_main", deployment_id="dpl_123")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/v13/deployments/dpl_123": MockResponse(
                200,
                {
                    "uid": "dpl_123",
                    "name": "rhumb-api",
                    "projectId": "prj_999",
                    "target": "production",
                },
            )
        }
    )

    with pytest.raises(VercelExecutorError) as exc:
        await get_deployment(request, bundle=bundle, client_factory=client_factory)

    assert exc.value.code == "deployment_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_deployment_returns_bounded_failure_metadata() -> None:
    request = DeploymentGetRequest(deployment_ref="dep_main", deployment_id="dpl_123")
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/v13/deployments/dpl_123": MockResponse(
                200,
                {
                    "uid": "dpl_123",
                    "name": "rhumb-api",
                    "projectId": "prj_123",
                    "target": "production",
                    "url": "rhumb-api.vercel.app",
                    "creator": {"uid": "user_1", "username": "pedro"},
                    "aliases": ["api.rhumb.dev"],
                    "error": {"code": "BUILD_FAILED", "message": "Build failed after install step"},
                },
            )
        }
    )

    response = await get_deployment(request, bundle=bundle, client_factory=client_factory)

    assert response.deployment_id == "dpl_123"
    assert response.project_id == "prj_123"
    assert response.aliases == ["api.rhumb.dev"]
    assert response.error_code == "BUILD_FAILED"
    assert response.error_message == "Build failed after install step"


def test_build_headers() -> None:
    bundle = _bundle(bearer_token="secret")

    headers = _build_headers(bundle)

    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Bearer secret"
