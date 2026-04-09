"""GitHub Actions workflow-run read-first executor for AUD-18."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import httpx

from schemas.actions_capabilities import (
    GitHubWorkflowRunSummary,
    WorkflowRunGetRequest,
    WorkflowRunGetResponse,
    WorkflowRunListRequest,
    WorkflowRunListResponse,
)
from services.actions_connection_registry import (
    ActionsRefError,
    GitHubActionsBundle,
    ensure_repository_allowed,
    split_repository,
)

GitHubClientFactory = Callable[..., Any]

_GITHUB_BASE_URL = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"


@dataclass(slots=True)
class GitHubActionsExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


async def list_workflow_runs(
    request: WorkflowRunListRequest,
    *,
    bundle: GitHubActionsBundle,
    client_factory: GitHubClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> WorkflowRunListResponse:
    try:
        repository = ensure_repository_allowed(bundle, request.repository)
        owner, repo = split_repository(repository)
    except ActionsRefError as exc:
        raise GitHubActionsExecutorError(
            code="workflow_run_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    params: dict[str, Any] = {
        "per_page": min(max(request.limit, 1), 25),
        "page": request.page,
    }
    if request.branch:
        params["branch"] = request.branch
    if request.status:
        params["status"] = request.status
    if request.event:
        params["event"] = request.event
    if request.exclude_pull_requests:
        params["exclude_pull_requests"] = "true"

    payload = await _github_get_json(
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/actions/runs",
        bundle=bundle,
        params=params,
        client_factory=client_factory,
        not_found_code="workflow_run_repository_not_found",
        not_found_message=f"GitHub repository '{repository}' not found",
    )

    raw_runs = payload.get("workflow_runs") or []
    if not isinstance(raw_runs, list):
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message="GitHub workflow-run list response was missing workflow_runs",
            status_code=503,
        )

    workflow_runs: list[GitHubWorkflowRunSummary] = []
    for item in raw_runs:
        if not isinstance(item, dict):
            continue
        run_id = _as_int(item.get("id"))
        if run_id is None:
            continue
        workflow_runs.append(_build_summary(item, repository=repository, run_id=run_id))

    total_count = _as_int(payload.get("total_count"))
    if total_count is not None:
        has_more = request.page * request.limit < total_count and len(workflow_runs) > 0
    else:
        has_more = len(workflow_runs) >= request.limit
    next_page = request.page + 1 if has_more else None

    return WorkflowRunListResponse(
        provider_used="github",
        credential_mode="byok",
        capability_id="workflow_run.list",
        receipt_id=receipt_id,
        execution_id=execution_id,
        actions_ref=bundle.actions_ref,
        repository=repository,
        workflow_runs=workflow_runs,
        run_count_returned=len(workflow_runs),
        total_count=total_count,
        has_more=has_more,
        next_page=next_page,
    )


async def get_workflow_run(
    request: WorkflowRunGetRequest,
    *,
    bundle: GitHubActionsBundle,
    client_factory: GitHubClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> WorkflowRunGetResponse:
    try:
        repository = ensure_repository_allowed(bundle, request.repository)
        owner, repo = split_repository(repository)
    except ActionsRefError as exc:
        raise GitHubActionsExecutorError(
            code="workflow_run_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    run = await _github_get_json(
        f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/actions/runs/{request.run_id}",
        bundle=bundle,
        params=None,
        client_factory=client_factory,
        not_found_code="workflow_run_not_found",
        not_found_message=f"GitHub Actions workflow run '{request.run_id}' not found",
    )

    if not isinstance(run, dict) or _as_int(run.get("id")) is None:
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message="GitHub workflow-run response was missing run payload",
            status_code=503,
        )

    return _build_get_response(
        request=request,
        bundle=bundle,
        repository=repository,
        run=run,
        receipt_id=receipt_id,
        execution_id=execution_id,
    )


async def _github_get_json(
    path: str,
    *,
    bundle: GitHubActionsBundle,
    params: dict[str, Any] | None,
    client_factory: GitHubClientFactory,
    not_found_code: str,
    not_found_message: str,
) -> dict[str, Any]:
    headers = _build_headers(bundle)
    try:
        async with client_factory(base_url=_GITHUB_BASE_URL, headers=headers, timeout=30.0) as client:
            response = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message=str(exc) or "GitHub request failed",
            status_code=503,
        ) from exc

    response_message = _response_message(response)
    if response.status_code == 404:
        raise GitHubActionsExecutorError(not_found_code, not_found_message, 404)
    if response.status_code == 429 or (response.status_code == 403 and "rate limit" in response_message.lower()):
        raise GitHubActionsExecutorError(
            code="workflow_run_rate_limited",
            message="GitHub rate limited the request",
            status_code=429,
        )
    if response.status_code in {401, 403}:
        raise GitHubActionsExecutorError(
            code="workflow_run_access_denied",
            message="GitHub denied access with the provided actions_ref credentials",
            status_code=response.status_code,
        )
    if response.status_code >= 500:
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message="GitHub upstream error",
            status_code=503,
        )
    if response.status_code >= 400:
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message=f"GitHub request failed with status {response.status_code}",
            status_code=502,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message="GitHub returned invalid JSON",
            status_code=503,
        ) from exc

    if not isinstance(payload, dict):
        raise GitHubActionsExecutorError(
            code="workflow_run_provider_unavailable",
            message="GitHub returned an unexpected response payload",
            status_code=503,
        )
    return payload


def _build_headers(bundle: GitHubActionsBundle) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {bundle.bearer_token}",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }


def _build_summary(run: dict[str, Any], *, repository: str, run_id: int) -> GitHubWorkflowRunSummary:
    return GitHubWorkflowRunSummary(
        run_id=run_id,
        workflow_id=_as_int(run.get("workflow_id")),
        repository=repository,
        workflow_name=_clean_text(run.get("name")),
        display_title=_clean_text(run.get("display_title")),
        run_number=_as_int(run.get("run_number")),
        event=_clean_text(run.get("event")),
        status=_clean_text(run.get("status")),
        conclusion=_clean_text(run.get("conclusion")),
        branch=_clean_text(run.get("head_branch")),
        head_sha=_clean_text(run.get("head_sha")),
        actor_login=_actor_login(run),
        html_url=_clean_text(run.get("html_url")),
        created_at=_clean_text(run.get("created_at")),
        updated_at=_clean_text(run.get("updated_at")),
        run_started_at=_clean_text(run.get("run_started_at")),
    )


def _build_get_response(
    *,
    request: WorkflowRunGetRequest,
    bundle: GitHubActionsBundle,
    repository: str,
    run: dict[str, Any],
    receipt_id: str,
    execution_id: str,
) -> WorkflowRunGetResponse:
    return WorkflowRunGetResponse(
        provider_used="github",
        credential_mode="byok",
        capability_id="workflow_run.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        actions_ref=bundle.actions_ref,
        repository=repository,
        run_id=_as_int(run.get("id")) or request.run_id,
        workflow_id=_as_int(run.get("workflow_id")),
        workflow_name=_clean_text(run.get("name")),
        display_title=_clean_text(run.get("display_title")),
        run_number=_as_int(run.get("run_number")),
        run_attempt=_as_int(run.get("run_attempt")),
        event=_clean_text(run.get("event")),
        status=_clean_text(run.get("status")),
        conclusion=_clean_text(run.get("conclusion")),
        branch=_clean_text(run.get("head_branch")),
        head_sha=_clean_text(run.get("head_sha")),
        actor_login=_actor_login(run),
        html_url=_clean_text(run.get("html_url")),
        created_at=_clean_text(run.get("created_at")),
        updated_at=_clean_text(run.get("updated_at")),
        run_started_at=_clean_text(run.get("run_started_at")),
    )


def _actor_login(run: dict[str, Any]) -> str | None:
    actor = run.get("actor")
    if not isinstance(actor, dict):
        return None
    return _clean_text(actor.get("login"))


def _response_message(response: Any) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str):
                return message
    except Exception:
        pass
    return ""


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
