"""Vercel deployment read-first executor for AUD-18."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import httpx

from schemas.deployment_capabilities import (
    DeploymentGetRequest,
    DeploymentGetResponse,
    DeploymentListRequest,
    DeploymentListResponse,
    VercelDeploymentSummary,
)
from services.deployment_connection_registry import (
    DeploymentRefError,
    VercelDeploymentBundle,
    deployment_in_scope,
    ensure_deployment_access,
    ensure_requested_project_allowed,
    ensure_target_allowed,
)

VercelClientFactory = Callable[..., Any]

_MAX_ERROR_TEXT_CHARS = 500
_VERCEL_BASE_URL = "https://api.vercel.com"


@dataclass(slots=True)
class VercelExecutorError(RuntimeError):
    code: str
    message: str
    status_code: int = 422

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


async def list_deployments(
    request: DeploymentListRequest,
    *,
    bundle: VercelDeploymentBundle,
    client_factory: VercelClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> DeploymentListResponse:
    try:
        ensure_requested_project_allowed(bundle, request.project_id)
        ensure_target_allowed(bundle, request.target)
    except DeploymentRefError as exc:
        raise VercelExecutorError(
            code="deployment_scope_denied" if "project" in str(exc) else "deployment_target_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    params: dict[str, Any] = {
        "limit": min(max(request.limit, 1), 25),
    }
    if bundle.team_id:
        params["teamId"] = bundle.team_id
    if request.project_id:
        params["projectId"] = request.project_id
    else:
        params["projectIds"] = list(bundle.allowed_project_ids)
    if request.target:
        params["target"] = request.target
    if request.state:
        params["state"] = request.state.upper()
    if request.created_after is not None:
        params["since"] = request.created_after
    until_value = request.page_after if request.page_after is not None else request.created_before
    if until_value is not None:
        params["until"] = until_value

    payload = await _vercel_get_json(
        "/v6/deployments",
        bundle=bundle,
        params=params,
        client_factory=client_factory,
        not_found_code="deployment_provider_unavailable",
        not_found_message="Vercel deployment list endpoint unavailable",
    )

    raw_deployments = payload.get("deployments") or []
    if not isinstance(raw_deployments, list):
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message="Vercel deployment list response was missing deployments",
            status_code=503,
        )

    deployments: list[VercelDeploymentSummary] = []
    for item in raw_deployments:
        if not isinstance(item, dict):
            continue
        if not deployment_in_scope(bundle, item):
            continue
        deployments.append(_build_summary(item))
        if len(deployments) >= request.limit:
            break

    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    next_page_after = _as_int(pagination.get("next"))

    return DeploymentListResponse(
        provider_used="vercel",
        credential_mode="byok",
        capability_id="deployment.list",
        receipt_id=receipt_id,
        execution_id=execution_id,
        deployment_ref=bundle.deployment_ref,
        deployments=deployments,
        deployment_count_returned=len(deployments),
        has_more=next_page_after is not None,
        next_page_after=next_page_after,
    )


async def get_deployment(
    request: DeploymentGetRequest,
    *,
    bundle: VercelDeploymentBundle,
    client_factory: VercelClientFactory = httpx.AsyncClient,
    receipt_id: str = "pending",
    execution_id: str = "pending",
) -> DeploymentGetResponse:
    params: dict[str, Any] = {}
    if bundle.team_id:
        params["teamId"] = bundle.team_id

    deployment = await _vercel_get_json(
        f"/v13/deployments/{quote(request.deployment_id, safe='')}",
        bundle=bundle,
        params=params,
        client_factory=client_factory,
        not_found_code="deployment_not_found",
        not_found_message=f"Vercel deployment '{request.deployment_id}' not found",
    )

    if not isinstance(deployment, dict) or not _deployment_id(deployment):
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message="Vercel deployment response was missing deployment payload",
            status_code=503,
        )

    try:
        ensure_deployment_access(bundle, deployment, deployment_id=request.deployment_id)
    except DeploymentRefError as exc:
        raise VercelExecutorError(
            code="deployment_scope_denied" if "deployment" in str(exc) else "deployment_target_scope_denied",
            message=str(exc),
            status_code=403,
        ) from exc

    return _build_get_response(
        request=request,
        bundle=bundle,
        deployment=deployment,
        receipt_id=receipt_id,
        execution_id=execution_id,
    )


async def _vercel_get_json(
    path: str,
    *,
    bundle: VercelDeploymentBundle,
    params: dict[str, Any] | None,
    client_factory: VercelClientFactory,
    not_found_code: str,
    not_found_message: str,
) -> dict[str, Any]:
    headers = _build_headers(bundle)
    try:
        async with client_factory(base_url=_VERCEL_BASE_URL, headers=headers, timeout=30.0) as client:
            response = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message=str(exc) or "Vercel request failed",
            status_code=503,
        ) from exc

    if response.status_code == 404:
        raise VercelExecutorError(not_found_code, not_found_message, 404)
    if response.status_code in {401, 403}:
        raise VercelExecutorError(
            code="deployment_access_denied",
            message="Vercel denied access with the provided deployment_ref credentials",
            status_code=response.status_code,
        )
    if response.status_code == 429:
        raise VercelExecutorError(
            code="deployment_rate_limited",
            message="Vercel rate limited the request",
            status_code=429,
        )
    if response.status_code >= 500:
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message="Vercel upstream error",
            status_code=503,
        )
    if response.status_code >= 400:
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message=f"Vercel request failed with status {response.status_code}",
            status_code=502,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message="Vercel returned invalid JSON",
            status_code=503,
        ) from exc

    if not isinstance(payload, dict):
        raise VercelExecutorError(
            code="deployment_provider_unavailable",
            message="Vercel returned an unexpected response payload",
            status_code=503,
        )
    return payload


def _build_headers(bundle: VercelDeploymentBundle) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {bundle.bearer_token}",
    }


def _build_summary(deployment: dict[str, Any]) -> VercelDeploymentSummary:
    return VercelDeploymentSummary(
        deployment_id=_deployment_id(deployment) or "unknown",
        project_id=_project_id(deployment) or "unknown",
        project_name=_project_name(deployment),
        target=_target(deployment),
        state=_state(deployment),
        url=_deployment_url(deployment),
        created_at=_as_int(deployment.get("createdAt") or deployment.get("created_at")),
        ready_at=_as_int(deployment.get("ready") or deployment.get("readyAt") or deployment.get("ready_at")),
        creator_id=_creator_id(deployment),
        creator_username=_creator_username(deployment),
        aliases=_aliases(deployment),
    )


def _build_get_response(
    *,
    request: DeploymentGetRequest,
    bundle: VercelDeploymentBundle,
    deployment: dict[str, Any],
    receipt_id: str,
    execution_id: str,
) -> DeploymentGetResponse:
    return DeploymentGetResponse(
        provider_used="vercel",
        credential_mode="byok",
        capability_id="deployment.get",
        receipt_id=receipt_id,
        execution_id=execution_id,
        deployment_ref=bundle.deployment_ref,
        deployment_id=_deployment_id(deployment) or request.deployment_id,
        project_id=_project_id(deployment) or "unknown",
        project_name=_project_name(deployment),
        target=_target(deployment),
        state=_state(deployment),
        url=_deployment_url(deployment),
        created_at=_as_int(deployment.get("createdAt") or deployment.get("created_at")),
        ready_at=_as_int(deployment.get("ready") or deployment.get("readyAt") or deployment.get("ready_at")),
        creator_id=_creator_id(deployment),
        creator_username=_creator_username(deployment),
        aliases=_aliases(deployment),
        error_code=_truncate(_error_field(deployment, "code"), _MAX_ERROR_TEXT_CHARS),
        error_message=_truncate(_error_field(deployment, "message"), _MAX_ERROR_TEXT_CHARS),
    )


def _deployment_id(deployment: dict[str, Any]) -> str | None:
    return _clean_text(deployment.get("uid") or deployment.get("id"))


def _project_id(deployment: dict[str, Any]) -> str | None:
    project = deployment.get("project")
    if isinstance(project, dict):
        nested = _clean_text(project.get("id"))
        if nested:
            return nested
    return _clean_text(deployment.get("projectId") or deployment.get("project_id"))


def _project_name(deployment: dict[str, Any]) -> str:
    project = deployment.get("project")
    if isinstance(project, dict):
        nested = _clean_text(project.get("name"))
        if nested:
            return nested
    return _clean_text(deployment.get("name")) or (_project_id(deployment) or "unknown")


def _target(deployment: dict[str, Any]) -> str | None:
    value = _clean_text(deployment.get("target"))
    return value.lower() if value else None


def _state(deployment: dict[str, Any]) -> str | None:
    value = _clean_text(
        deployment.get("readyState")
        or deployment.get("ready_state")
        or deployment.get("state")
        or deployment.get("status")
    )
    return value.lower() if value else None


def _deployment_url(deployment: dict[str, Any]) -> str | None:
    url = _clean_text(deployment.get("url"))
    if url is None:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://{url}"


def _creator_id(deployment: dict[str, Any]) -> str | None:
    creator = deployment.get("creator")
    if not isinstance(creator, dict):
        return None
    return _clean_text(creator.get("uid") or creator.get("id"))


def _creator_username(deployment: dict[str, Any]) -> str | None:
    creator = deployment.get("creator")
    if not isinstance(creator, dict):
        return None
    return _clean_text(creator.get("username") or creator.get("email") or creator.get("name"))


def _aliases(deployment: dict[str, Any]) -> list[str]:
    raw_aliases = deployment.get("aliases") or deployment.get("alias") or []
    values: list[str] = []
    if isinstance(raw_aliases, list):
        for item in raw_aliases:
            if isinstance(item, str):
                text = _clean_text(item)
            elif isinstance(item, dict):
                text = _clean_text(item.get("alias") or item.get("domain") or item.get("name"))
            else:
                text = None
            if text:
                values.append(text)
    elif isinstance(raw_aliases, str):
        text = _clean_text(raw_aliases)
        if text:
            values.append(text)
    return values[:10]


def _error_field(deployment: dict[str, Any], field_name: str) -> str | None:
    error = deployment.get("error")
    if isinstance(error, dict):
        return _clean_text(error.get(field_name))
    if field_name == "message":
        return _clean_text(deployment.get("errorMessage") or deployment.get("error_message"))
    if field_name == "code":
        return _clean_text(deployment.get("errorCode") or deployment.get("error_code"))
    return None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truncate(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3] + "..."
