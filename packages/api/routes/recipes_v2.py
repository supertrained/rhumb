"""Resolve v2 recipe endpoints (Layer 3 deterministic composition)."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from copy import deepcopy
from datetime import timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from routes._supabase import supabase_fetch, supabase_insert
from routes.resolve_v2 import _forward_internal, _resolve_policy_agent
from services.error_envelope import RhumbError
from services.kill_switches import init_kill_switch_registry
from services.recipe_engine import (
    RecipeDefinition,
    RecipeEngine,
    RecipeExecution,
    RecipeStatus,
    StepDefinition,
    StepExecutor,
    StepResult,
    StepStatus,
    compile_recipe,
)
from services.recipe_safety import RecipeSafetyGate, get_safety_gate

router = APIRouter()

_LAYER = 3
_VERSION = "2026-03-31"


class RecipeExecuteRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    credential_mode: str = Field(default="rhumb_managed")
    interface: str = Field(default="rest")
    idempotency_key: str | None = Field(default=None)
    policy: dict[str, Any] | None = Field(
        default=None,
        description="Optional Layer 2 provider policy forwarded to every step execution.",
    )


def _compat_headers() -> dict[str, str]:
    return {
        "X-Rhumb-Version": _VERSION,
        "X-Rhumb-Layer": str(_LAYER),
    }


def _json_response(status_code: int, content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content, headers=_compat_headers())


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_recipe_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "recipe_id": row.get("recipe_id"),
        "name": row.get("name"),
        "version": row.get("version"),
        "category": row.get("category"),
        "stability": row.get("stability"),
        "tier": row.get("tier"),
        "step_count": row.get("step_count"),
        "max_total_cost_usd": row.get("max_total_cost_usd"),
        "published": bool(row.get("published", False)),
        "updated_at": row.get("updated_at"),
    }


def _normalize_recipe_detail(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_normalize_recipe_summary(row),
        "definition": row.get("definition") or {},
        "inputs_schema": row.get("inputs_schema") or {},
        "outputs_schema": row.get("outputs_schema") or {},
        "layer": _LAYER,
    }


async def _fetch_recipe_row(recipe_id: str) -> dict[str, Any] | None:
    rows = await supabase_fetch(
        "recipes"
        "?select=recipe_id,name,version,category,stability,tier,definition,inputs_schema,outputs_schema,step_count,max_total_cost_usd,published,updated_at"
        f"&recipe_id=eq.{quote(recipe_id)}"
        "&published=eq.true"
        "&limit=1"
    ) or []
    if not rows:
        return None
    return rows[0]


async def _fetch_execution_rows(execution_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    execution_rows = await supabase_fetch(
        "recipe_executions"
        "?select=execution_id,recipe_id,status,inputs,total_cost_usd,total_duration_ms,step_count,steps_completed,error,started_at,completed_at,org_id,agent_id,credential_mode"
        f"&execution_id=eq.{quote(execution_id)}"
        "&limit=1"
    ) or []
    step_rows = await supabase_fetch(
        "recipe_step_executions"
        "?select=execution_id,step_id,capability_id,status,cost_usd,duration_ms,receipt_id,provider_used,retries_used,error,outputs"
        f"&execution_id=eq.{quote(execution_id)}"
        "&order=id.asc"
    ) or []
    return (execution_rows[0] if execution_rows else None, step_rows)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _status_code_for_recipe(recipe_status: str) -> int:
    if recipe_status == RecipeStatus.BUDGET_EXCEEDED.value:
        return 402
    if recipe_status == RecipeStatus.TIMED_OUT.value:
        return 504
    if recipe_status == RecipeStatus.FAILED.value:
        return 422
    return 200


def _build_step_result_payload(step: StepDefinition | None, result: StepResult) -> dict[str, Any]:
    return {
        "step_id": result.step_id,
        "capability_id": step.capability_id if step else None,
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "outputs": result.outputs,
        "cost_usd": result.cost_usd,
        "duration_ms": result.duration_ms,
        "receipt_id": result.receipt_id,
        "error": result.error,
        "retries_used": result.retries_used,
        "provider_used": result.provider_used,
    }


def _terminal_outputs(recipe: RecipeDefinition, execution: RecipeExecution) -> dict[str, Any]:
    depended_on = {dep for step in recipe.steps for dep in step.depends_on}
    terminal_ids = [step.step_id for step in recipe.steps if step.step_id not in depended_on]
    outputs: dict[str, Any] = {}
    for step_id in terminal_ids:
        result = execution.step_results.get(step_id)
        if result and result.status == StepStatus.SUCCEEDED:
            outputs[step_id] = result.outputs
    return outputs


def _build_execution_payload(
    recipe: RecipeDefinition,
    execution: RecipeExecution,
    *,
    deduplicated: bool = False,
) -> dict[str, Any]:
    steps_by_id = {step.step_id: step for step in recipe.steps}
    return {
        "execution_id": execution.execution_id,
        "recipe_id": execution.recipe_id,
        "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        "total_cost_usd": execution.total_cost_usd,
        "total_duration_ms": execution.total_duration_ms,
        "started_at": _iso(execution.started_at),
        "completed_at": _iso(execution.completed_at),
        "error": execution.error,
        "receipt_chain_hash": execution.receipt_chain_hash,
        "deduplicated": deduplicated,
        "layer": _LAYER,
        "outputs": _terminal_outputs(recipe, execution),
        "step_results": [
            _build_step_result_payload(steps_by_id.get(step_id), result)
            for step_id, result in execution.step_results.items()
        ],
    }


def _build_execution_payload_from_rows(
    recipe: RecipeDefinition,
    execution_row: Mapping[str, Any],
    step_rows: list[Mapping[str, Any]],
    *,
    deduplicated: bool = False,
) -> dict[str, Any]:
    step_results = [
        {
            "step_id": row.get("step_id"),
            "capability_id": row.get("capability_id"),
            "status": row.get("status"),
            "outputs": row.get("outputs") or {},
            "cost_usd": row.get("cost_usd", 0.0),
            "duration_ms": row.get("duration_ms", 0),
            "receipt_id": row.get("receipt_id"),
            "error": row.get("error"),
            "retries_used": row.get("retries_used", 0),
            "provider_used": row.get("provider_used"),
        }
        for row in step_rows
    ]
    depended_on = {dep for step in recipe.steps for dep in step.depends_on}
    terminal_ids = {step.step_id for step in recipe.steps if step.step_id not in depended_on}
    outputs = {
        row.get("step_id"): row.get("outputs") or {}
        for row in step_rows
        if row.get("step_id") in terminal_ids and row.get("status") == StepStatus.SUCCEEDED.value
    }
    receipt_hash = _hash_payload([row.get("receipt_id") for row in step_rows if row.get("receipt_id")])
    return {
        "execution_id": execution_row.get("execution_id"),
        "recipe_id": execution_row.get("recipe_id"),
        "status": execution_row.get("status"),
        "total_cost_usd": execution_row.get("total_cost_usd", 0.0),
        "total_duration_ms": execution_row.get("total_duration_ms", 0),
        "started_at": execution_row.get("started_at"),
        "completed_at": execution_row.get("completed_at"),
        "error": execution_row.get("error"),
        "receipt_chain_hash": receipt_hash,
        "deduplicated": deduplicated,
        "layer": _LAYER,
        "outputs": outputs,
        "step_results": step_results,
    }


class _InternalRecipeStepExecutor(StepExecutor):
    def __init__(
        self,
        *,
        raw_request: Request,
        payload: RecipeExecuteRequest,
        safety_gate: RecipeSafetyGate,
        execution_id: str,
    ) -> None:
        self._raw_request = raw_request
        self._payload = payload
        self._safety_gate = safety_gate
        self._execution_id = execution_id

    async def execute_step(
        self,
        step: StepDefinition,
        resolved_params: dict[str, Any],
        credential_mode: str = "rhumb_managed",
    ) -> StepResult:
        if not self._safety_gate.rate_limiter.check(self._execution_id):
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="Fan-out rate limit exceeded during recipe execution",
            )

        input_firewall = self._safety_gate.firewall.inspect(
            resolved_params,
            context=f"recipe_step_input:{step.step_id}",
        )
        if not input_firewall.passed:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="Content firewall blocked resolved step inputs",
            )

        step_policy = deepcopy(self._payload.policy) if self._payload.policy else None
        response = await _forward_internal(
            self._raw_request,
            method="POST",
            path=f"/v2/capabilities/{step.capability_id}/execute",
            json_body={
                "parameters": resolved_params,
                "credential_mode": credential_mode,
                "interface": self._payload.interface,
                **({"policy": step_policy} if step_policy else {}),
            },
        )
        body = response.json() if hasattr(response, "json") else {}
        data = body.get("data") if isinstance(body, dict) else {}
        error = body.get("error") if isinstance(body, dict) else {}
        upstream_response = data.get("upstream_response") if isinstance(data, dict) else None
        root_outputs = {
            "result": upstream_response if isinstance(upstream_response, dict) else (upstream_response or {}),
            "provider_used": data.get("provider_used") if isinstance(data, dict) else None,
            "receipt_id": data.get("receipt_id") if isinstance(data, dict) else None,
            "execution_id": data.get("execution_id") if isinstance(data, dict) else None,
        }
        captured_outputs = _capture_outputs(root_outputs, step.outputs_captured)

        output_firewall = self._safety_gate.check_step_transition(
            captured_outputs or root_outputs,
            context=f"recipe_step_output:{step.step_id}",
        )
        if not output_firewall.passed:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="Content firewall blocked step outputs",
            )

        if response.status_code == 200:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.SUCCEEDED,
                outputs=captured_outputs or root_outputs,
                cost_usd=float(data.get("cost_estimate_usd") or 0.0),
                duration_ms=int(data.get("latency_ms") or 0),
                receipt_id=str(data.get("receipt_id") or ""),
                provider_used=data.get("provider_used"),
            )

        if response.status_code == 402:
            status = StepStatus.BUDGET_EXCEEDED
        elif response.status_code == 504:
            status = StepStatus.TIMED_OUT
        else:
            status = StepStatus.FAILED

        error_message = None
        if isinstance(error, dict):
            error_message = error.get("message") or error.get("detail") or error.get("code")
        return StepResult(
            step_id=step.step_id,
            status=status,
            outputs={},
            cost_usd=float(data.get("cost_estimate_usd") or 0.0) if isinstance(data, dict) else 0.0,
            duration_ms=int(data.get("latency_ms") or 0) if isinstance(data, dict) else 0,
            receipt_id=str(data.get("receipt_id") or "") if isinstance(data, dict) else "",
            error=error_message or f"Capability execution failed with status {response.status_code}",
            provider_used=data.get("provider_used") if isinstance(data, dict) else None,
        )


def _lookup_path(payload: Any, path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current



def _capture_outputs(root_outputs: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    if not mapping:
        return {}
    captured: dict[str, Any] = {}
    for output_key, source_path in mapping.items():
        try:
            captured[output_key] = _lookup_path(root_outputs, source_path)
        except KeyError:
            continue
    return captured


async def _persist_execution(
    recipe: RecipeDefinition,
    execution: RecipeExecution,
    *,
    inputs: dict[str, Any],
    agent_id: str | None,
    org_id: str | None,
    credential_mode: str,
) -> None:
    await supabase_insert(
        "recipe_executions",
        {
            "execution_id": execution.execution_id,
            "recipe_id": recipe.recipe_id,
            "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
            "inputs": inputs,
            "total_cost_usd": execution.total_cost_usd,
            "total_duration_ms": execution.total_duration_ms,
            "step_count": len(recipe.steps),
            "steps_completed": sum(1 for result in execution.step_results.values() if result.status == StepStatus.SUCCEEDED),
            "error": execution.error,
            "started_at": execution.started_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "org_id": org_id,
            "agent_id": agent_id,
            "credential_mode": credential_mode,
        },
    )

    steps_by_id = {step.step_id: step for step in recipe.steps}
    for step_id, result in execution.step_results.items():
        step = steps_by_id.get(step_id)
        await supabase_insert(
            "recipe_step_executions",
            {
                "execution_id": execution.execution_id,
                "step_id": step_id,
                "capability_id": step.capability_id if step else "",
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
                "receipt_id": result.receipt_id or None,
                "provider_used": result.provider_used,
                "retries_used": result.retries_used,
                "error": result.error,
                "outputs": result.outputs,
                "started_at": execution.started_at.isoformat(),
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            },
        )


@router.get("/recipes")
async def list_recipes(
    category: str | None = Query(default=None, description="Filter by recipe category"),
    stability: str | None = Query(default=None, description="Filter by recipe stability"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    query = (
        "recipes"
        "?select=recipe_id,name,version,category,stability,tier,step_count,max_total_cost_usd,published,updated_at"
        "&published=eq.true"
        "&order=updated_at.desc.nullslast,recipe_id.asc"
        f"&limit={limit}&offset={offset}"
    )
    if category:
        query += f"&category=eq.{quote(category)}"
    if stability:
        query += f"&stability=eq.{quote(stability)}"

    rows = await supabase_fetch(query) or []
    return _json_response(
        200,
        {
            "data": {
                "recipes": [_normalize_recipe_summary(row) for row in rows],
                "count": len(rows),
                "limit": limit,
                "offset": offset,
                "layer": _LAYER,
            },
            "error": None,
        },
    )


@router.get("/recipes/{recipe_id}")
async def get_recipe(recipe_id: str) -> JSONResponse:
    row = await _fetch_recipe_row(recipe_id)
    if row is None:
        raise RhumbError(
            "RECIPE_NOT_FOUND",
            message=f"No published recipe found with id '{recipe_id}'",
            detail="Check the recipe_id from /v2/recipes and ensure the recipe is published.",
        )

    return _json_response(200, {"data": _normalize_recipe_detail(row), "error": None})


@router.post("/recipes/{recipe_id}/execute")
async def execute_recipe(
    recipe_id: str,
    payload: RecipeExecuteRequest,
    raw_request: Request,
    x_rhumb_idempotency_key: str | None = Header(None, alias="X-Rhumb-Idempotency-Key"),
) -> JSONResponse:
    api_key = raw_request.headers.get("X-Rhumb-Key")
    if not api_key:
        raise RhumbError(
            "CREDENTIAL_MISSING",
            message="Recipe execution requires a Rhumb API key.",
            detail="Provide X-Rhumb-Key for Layer 3 recipe execution.",
        )

    agent = await _resolve_policy_agent(raw_request)
    row = await _fetch_recipe_row(recipe_id)
    if row is None:
        raise RhumbError(
            "RECIPE_NOT_FOUND",
            message=f"No published recipe found with id '{recipe_id}'",
            detail="Check the recipe_id from /v2/recipes and ensure the recipe is published.",
        )

    raw_definition = row.get("definition")
    if not isinstance(raw_definition, dict):
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Stored recipe definition is invalid.",
            detail="Recipe definition must be a JSON object.",
        )

    try:
        recipe = compile_recipe(deepcopy(raw_definition))
    except Exception as exc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Recipe definition failed validation.",
            detail=str(exc),
        ) from exc

    kill_switch_registry = await init_kill_switch_registry()
    blocked, kill_reason = kill_switch_registry.is_blocked(
        agent_id=agent.agent_id,
        recipe_id=recipe.recipe_id,
        operation_class="financial",
        require_authoritative=True,
    )
    if blocked:
        raise RhumbError(
            "PROVIDER_UNAVAILABLE",
            message="Recipe execution is temporarily blocked by a kill switch.",
            detail=kill_reason,
        )

    effective_idempotency_key = payload.idempotency_key or x_rhumb_idempotency_key
    execution_id = f"rexec_{uuid.uuid4().hex[:24]}"
    safety_gate = get_safety_gate()
    preflight = safety_gate.check_pre_execution(
        recipe_id=recipe.recipe_id,
        inputs=payload.inputs,
        chain_id=execution_id,
        execution_id=execution_id,
        agent_id=agent.agent_id,
        idempotency_key=effective_idempotency_key,
    )

    if preflight.idempotency_hit is not None:
        execution_row, step_rows = await _fetch_execution_rows(preflight.idempotency_hit.execution_id)
        if execution_row is not None:
            replay_payload = _build_execution_payload_from_rows(
                recipe,
                execution_row,
                step_rows,
                deduplicated=True,
            )
        else:
            replay_payload = {
                "execution_id": preflight.idempotency_hit.execution_id,
                "recipe_id": preflight.idempotency_hit.recipe_id,
                "status": preflight.idempotency_hit.status,
                "deduplicated": True,
                "layer": _LAYER,
                "outputs": {},
                "step_results": [],
                "receipt_chain_hash": preflight.idempotency_hit.result_hash,
            }
        return _json_response(200, {"data": replay_payload, "error": None})

    if not preflight.passed:
        if preflight.rate_limited:
            raise RhumbError(
                "RATE_LIMITED",
                message="Recipe execution hit the Layer 3 rate limiter.",
                detail=preflight.reason,
            )
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Recipe execution blocked by safety policy.",
            detail=preflight.reason,
        )

    engine = RecipeEngine(
        step_executor=_InternalRecipeStepExecutor(
            raw_request=raw_request,
            payload=payload,
            safety_gate=safety_gate,
            execution_id=execution_id,
        )
    )
    execution = await engine.execute(recipe, payload.inputs, credential_mode=payload.credential_mode)
    execution.execution_id = execution_id
    execution.receipt_chain_hash = _hash_payload(
        [
            result.receipt_id
            for result in execution.step_results.values()
            if result.receipt_id
        ]
    )

    if execution.status == RecipeStatus.BUDGET_EXCEEDED:
        execution.error = execution.error or "Recipe budget exceeded during execution"
    elif execution.status == RecipeStatus.TIMED_OUT:
        execution.error = execution.error or "Recipe execution timed out"
    elif execution.status == RecipeStatus.FAILED:
        execution.error = execution.error or "One or more recipe steps failed"

    await _persist_execution(
        recipe,
        execution,
        inputs=payload.inputs,
        agent_id=agent.agent_id,
        org_id=agent.organization_id,
        credential_mode=payload.credential_mode,
    )

    safety_gate.finalize_execution(
        chain_id=execution_id,
        execution_id=execution_id,
        idempotency_key=effective_idempotency_key,
        recipe_id=recipe.recipe_id,
        status=execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        result_hash=execution.receipt_chain_hash,
    )

    response_payload = _build_execution_payload(recipe, execution)
    return _json_response(
        _status_code_for_recipe(response_payload["status"]),
        {"data": response_payload, "error": None},
    )
