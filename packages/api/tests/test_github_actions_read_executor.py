"""Tests for the GitHub Actions workflow-run read-first executor."""

from __future__ import annotations

import pytest

from schemas.actions_capabilities import WorkflowRunGetRequest, WorkflowRunListRequest
from services.actions_connection_registry import GitHubActionsBundle
from services.github_actions_read_executor import (
    GitHubActionsExecutorError,
    _build_headers,
    get_workflow_run,
    list_workflow_runs,
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


def _bundle(**overrides) -> GitHubActionsBundle:
    data = {
        "actions_ref": "gh_main",
        "provider": "github",
        "auth_mode": "bearer_token",
        "bearer_token": "token-123",
        "allowed_repositories": ("openclaw/openclaw",),
    }
    data.update(overrides)
    return GitHubActionsBundle(**data)


@pytest.mark.asyncio
async def test_list_workflow_runs_returns_bounded_metadata() -> None:
    request = WorkflowRunListRequest(actions_ref="gh_main", repository="openclaw/openclaw", limit=2, page=1)
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/repos/openclaw/openclaw/actions/runs": MockResponse(
                200,
                {
                    "total_count": 3,
                    "workflow_runs": [
                        {
                            "id": 101,
                            "workflow_id": 9001,
                            "name": "CI",
                            "display_title": "Fix lint",
                            "run_number": 55,
                            "event": "push",
                            "status": "completed",
                            "conclusion": "success",
                            "head_branch": "main",
                            "head_sha": "abc123",
                            "actor": {"login": "pedro"},
                            "html_url": "https://github.com/openclaw/openclaw/actions/runs/101",
                            "created_at": "2026-04-09T16:00:00Z",
                            "updated_at": "2026-04-09T16:01:00Z",
                        },
                        {
                            "id": 102,
                            "workflow_id": 9001,
                            "name": "CI",
                            "display_title": "Fix tests",
                            "run_number": 56,
                            "event": "pull_request",
                            "status": "in_progress",
                            "conclusion": None,
                            "head_branch": "feature/thing",
                            "head_sha": "def456",
                            "actor": {"login": "tom"},
                            "html_url": "https://github.com/openclaw/openclaw/actions/runs/102",
                            "created_at": "2026-04-09T17:00:00Z",
                            "updated_at": "2026-04-09T17:01:00Z",
                        },
                    ],
                },
            )
        }
    )

    response = await list_workflow_runs(request, bundle=bundle, client_factory=client_factory)

    assert response.run_count_returned == 2
    assert response.workflow_runs[0].run_id == 101
    assert response.workflow_runs[0].workflow_name == "CI"
    assert response.workflow_runs[1].actor_login == "tom"
    assert response.total_count == 3
    assert response.has_more is True
    assert response.next_page == 2


@pytest.mark.asyncio
async def test_list_workflow_runs_rejects_out_of_scope_repository() -> None:
    request = WorkflowRunListRequest(actions_ref="gh_main", repository="octo/test")
    bundle = _bundle()

    with pytest.raises(GitHubActionsExecutorError) as exc:
        await list_workflow_runs(request, bundle=bundle, client_factory=lambda **kwargs: MockAsyncClient(responses={}))

    assert exc.value.code == "workflow_run_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_workflow_run_maps_not_found() -> None:
    request = WorkflowRunGetRequest(actions_ref="gh_main", repository="openclaw/openclaw", run_id=999)
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/repos/openclaw/openclaw/actions/runs/999": MockResponse(404, {"message": "Not Found"})
        }
    )

    with pytest.raises(GitHubActionsExecutorError) as exc:
        await get_workflow_run(request, bundle=bundle, client_factory=client_factory)

    assert exc.value.code == "workflow_run_not_found"
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_workflow_run_returns_bounded_metadata() -> None:
    request = WorkflowRunGetRequest(actions_ref="gh_main", repository="openclaw/openclaw", run_id=101)
    bundle = _bundle()
    client_factory = lambda **kwargs: MockAsyncClient(
        responses={
            "/repos/openclaw/openclaw/actions/runs/101": MockResponse(
                200,
                {
                    "id": 101,
                    "workflow_id": 9001,
                    "name": "CI",
                    "display_title": "Fix lint",
                    "run_number": 55,
                    "run_attempt": 1,
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "head_sha": "abc123",
                    "actor": {"login": "pedro"},
                    "html_url": "https://github.com/openclaw/openclaw/actions/runs/101",
                    "created_at": "2026-04-09T16:00:00Z",
                    "updated_at": "2026-04-09T16:01:00Z",
                    "run_started_at": "2026-04-09T16:00:10Z",
                },
            )
        }
    )

    response = await get_workflow_run(request, bundle=bundle, client_factory=client_factory)

    assert response.run_id == 101
    assert response.workflow_id == 9001
    assert response.run_attempt == 1
    assert response.actor_login == "pedro"


def test_build_headers() -> None:
    bundle = _bundle(bearer_token="secret")

    headers = _build_headers(bundle)

    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["Authorization"] == "Bearer secret"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
