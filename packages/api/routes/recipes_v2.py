"""Resolve v2 recipe endpoints (Layer 3 deterministic composition)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from copy import deepcopy
from datetime import timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from routes._supabase import (
    SupabaseWriteUnavailable,
    supabase_fetch,
    supabase_insert,
    supabase_insert_required,
    supabase_patch_required,
)
from routes.resolve_v2 import _forward_internal, _resolve_policy_agent
from services.durable_event_persistence import get_event_outbox_health
from services.durable_idempotency import DurableIdempotencyStore, IdempotencyUnavailable
from services.durable_rate_limit import DurableRateLimiter
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
from services.service_slugs import CANONICAL_TO_PROXY, public_service_slug, public_service_slug_candidates

router = APIRouter()

_LAYER = 3
_VERSION = "2026-03-31"

_idempotency_store: DurableIdempotencyStore | None = None
_recipe_step_rate_limiter: DurableRateLimiter | None = None

_RECIPE_FANOUT_ORG_LIMIT = 500
_RECIPE_FANOUT_GLOBAL_LIMIT = 2000
_RECIPE_FANOUT_WINDOW_SECONDS = 60

_RECIPE_STABILITY_FILTERS = ("stable", "beta", "all")
_RECIPE_STABILITY_FILTER_SET = set(_RECIPE_STABILITY_FILTERS)


class RecipeExecuteRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    credential_mode: str = Field(default="rhumb_managed")
    interface: str = Field(default="rest")
    idempotency_key: str | None = Field(default=None)
    policy: dict[str, Any] | None = Field(
        default=None,
        description="Optional Layer 2 provider policy forwarded to every step execution.",
    )


async def _get_idempotency_store() -> DurableIdempotencyStore:
    global _idempotency_store
    if _idempotency_store is None:
        from db.client import get_supabase_client

        supabase = await get_supabase_client()
        _idempotency_store = DurableIdempotencyStore(supabase)
    return _idempotency_store


async def _get_recipe_step_rate_limiter() -> DurableRateLimiter:
    global _recipe_step_rate_limiter
    if _recipe_step_rate_limiter is None:
        from db.client import get_supabase_client

        try:
            supabase = await get_supabase_client()
        except Exception:
            class _UnavailableSupabaseClient:
                def rpc(self, *_args, **_kwargs):
                    raise RuntimeError("supabase_unavailable")

                def table(self, *_args, **_kwargs):
                    raise RuntimeError("supabase_unavailable")

            supabase = _UnavailableSupabaseClient()

        _recipe_step_rate_limiter = DurableRateLimiter(supabase)
    return _recipe_step_rate_limiter


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


def _validated_recipe_stability_filter(stability: str | None) -> str | None:
    if stability is None:
        return None

    normalized = stability.strip().lower()
    if normalized == "all":
        return None
    if normalized in _RECIPE_STABILITY_FILTER_SET:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'stability' filter.",
        detail="Use one of: stable, beta, all.",
    )


def _canonicalize_recipe_category(category: str | None) -> str | None:
    if category is None:
        return None

    normalized = category.strip().lower()
    return normalized or None


def _validated_recipe_category_before_reads(category: str | None) -> str | None:
    if category is None:
        return None

    normalized = category.strip().lower()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'category' filter.",
        detail="Provide a non-empty category filter.",
    )


def _validated_recipe_list_limit(limit: int) -> int:
    if 1 <= limit <= 200:
        return limit

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'limit' filter.",
        detail="Provide an integer between 1 and 200.",
    )


def _validated_recipe_list_offset(offset: int) -> int:
    if offset >= 0:
        return offset

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'offset' filter.",
        detail="Provide an integer greater than or equal to 0.",
    )


async def _available_recipe_categories() -> set[str]:
    rows = await supabase_fetch("recipes?select=category&published=eq.true") or []
    return {
        str(row.get("category")).strip().lower()
        for row in rows
        if str(row.get("category") or "").strip()
    }


def _validated_recipe_category(
    category: str | None,
    *,
    available_categories: set[str],
) -> str | None:
    normalized = _canonicalize_recipe_category(category)
    if normalized is None:
        return None
    if not available_categories or normalized in available_categories:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'category' filter.",
        detail=f"Use one of: {', '.join(sorted(available_categories))}.",
    )


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


def _public_provider_used(provider_used: str | None) -> str | None:
    return public_service_slug(provider_used) or provider_used


def _canonicalize_known_provider_aliases(text: Any) -> str | None:
    if text is None:
        return None

    replacements: dict[str, str] = {}
    for canonical in CANONICAL_TO_PROXY:
        for candidate in public_service_slug_candidates(canonical):
            cleaned = str(candidate or "").strip()
            if not cleaned or cleaned.lower() == canonical.lower():
                continue
            replacements[cleaned.lower()] = canonical

    if not replacements:
        return str(text)

    pattern = re.compile(
        rf"(?<![a-z0-9-])(?:{'|'.join(re.escape(candidate) for candidate in sorted(replacements, key=len, reverse=True))})(?![a-z0-9-])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: replacements[match.group(0).lower()], str(text))


def _canonicalize_provider_text(text: Any, provider_used: Any) -> str | None:
    if text is None:
        return None

    canonical = _public_provider_used(provider_used)
    if canonical is None:
        return str(text)

    raw_provider_used = str(provider_used).strip().lower() if provider_used else None
    if raw_provider_used == canonical.lower():
        return str(text)

    canonicalized = str(text)
    for candidate in sorted(public_service_slug_candidates(canonical), key=len, reverse=True):
        if not candidate or candidate == canonical:
            continue
        canonicalized = re.sub(
            rf"(?<![a-z0-9-]){re.escape(candidate)}(?![a-z0-9-])",
            canonical,
            canonicalized,
            flags=re.IGNORECASE,
        )
    return canonicalized


def _canonicalize_provider_text_from_contexts(text: Any, provider_values: list[Any]) -> str | None:
    if text is None:
        return None

    canonicalized = str(text)
    seen: set[str] = set()
    for provider_value in provider_values:
        provider_key = str(provider_value or "").strip()
        if not provider_key:
            continue
        canonical = public_service_slug(provider_key) or provider_key.lower()
        if canonical in seen:
            continue
        seen.add(canonical)
        canonicalized = _canonicalize_provider_text(canonicalized, canonical) or canonicalized
    return _canonicalize_known_provider_aliases(canonicalized)


_PROVIDER_VALUE_KEYS = {
    "provider",
    "provider_used",
    "provider_id",
    "provider_slug",
    "selected_provider",
    "requested_provider",
    "fallback_provider",
}


_PROVIDER_LIST_KEYS = {
    "available_providers",
    "candidate_providers",
    "fallback_providers",
    "supported_provider_slugs",
    "unavailable_provider_slugs",
    "not_execute_ready_provider_slugs",
    "policy_candidates",
}


_PROVIDER_TEXT_KEYS = {"message", "detail", "error_message"}


def _merge_provider_contexts(*values: Any) -> list[Any]:
    contexts: list[Any] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            contexts.extend(_merge_provider_contexts(*value))
            continue
        contexts.append(value)
    return contexts


def _provider_contexts_from_payload(value: Any) -> list[str]:
    contexts: list[str] = []

    def _append_context(raw_value: Any) -> None:
        if raw_value is None:
            return
        if isinstance(raw_value, (list, tuple, set)):
            for entry in raw_value:
                _append_context(entry)
            return
        if isinstance(raw_value, Mapping):
            return
        provider_key = str(raw_value).strip()
        if provider_key:
            contexts.append(provider_key)

    def _walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if key in _PROVIDER_VALUE_KEYS:
                    _append_context(nested)
                elif key in _PROVIDER_LIST_KEYS:
                    _append_context(nested)
                _walk(nested)
            return
        if isinstance(item, list):
            for nested in item:
                _walk(nested)

    _walk(value)
    return contexts


def _provider_contexts_from_captured_outputs(
    outputs: Mapping[str, Any],
    capture_paths: Mapping[str, str],
) -> list[Any]:
    contexts: list[Any] = []
    for output_key, source_path in capture_paths.items():
        if output_key not in outputs:
            continue
        source_key = str(source_path or "").split(".")[-1]
        if source_path == "provider_used" or source_key in _PROVIDER_VALUE_KEYS:
            contexts.extend(_merge_provider_contexts(outputs.get(output_key)))
        elif source_key in _PROVIDER_LIST_KEYS:
            contexts.extend(_merge_provider_contexts(outputs.get(output_key)))
    return contexts


def _canonicalize_provider_value(value: Any) -> Any:
    if isinstance(value, str):
        public_slug = _public_provider_used(value)
        return public_slug or value
    return value


def _canonicalize_provider_payload(value: Any, *, provider_contexts: list[Any]) -> Any:
    if isinstance(value, dict):
        local_contexts = _merge_provider_contexts(
            provider_contexts,
            _provider_contexts_from_payload(value),
        )
        canonicalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PROVIDER_VALUE_KEYS:
                canonicalized[key] = _canonicalize_provider_value(item)
            elif key in _PROVIDER_TEXT_KEYS:
                canonicalized[key] = _canonicalize_provider_text_from_contexts(item, local_contexts)
            elif key in _PROVIDER_LIST_KEYS and isinstance(item, list):
                canonicalized[key] = [_canonicalize_provider_value(entry) for entry in item]
            else:
                canonicalized[key] = _canonicalize_provider_payload(
                    item,
                    provider_contexts=local_contexts,
                )
        return canonicalized
    if isinstance(value, list):
        return [
            _canonicalize_provider_payload(item, provider_contexts=provider_contexts)
            for item in value
        ]
    return value


def _public_step_outputs(step: StepDefinition | None, outputs: Any, *, provider_used: Any) -> Any:
    if not isinstance(outputs, Mapping):
        return outputs

    capture_paths = dict(step.outputs_captured or {}) if step else {}
    provider_contexts = _merge_provider_contexts(
        provider_used,
        _provider_contexts_from_payload(outputs),
        _provider_contexts_from_captured_outputs(outputs, capture_paths),
    )
    normalized = _canonicalize_provider_payload(
        dict(outputs),
        provider_contexts=provider_contexts,
    )

    for output_key, source_path in capture_paths.items():
        if output_key not in normalized:
            continue
        source_key = str(source_path or "").split(".")[-1]
        if source_path == "provider_used" or source_key in _PROVIDER_VALUE_KEYS:
            normalized[output_key] = _canonicalize_provider_value(normalized.get(output_key))
        elif source_key in _PROVIDER_LIST_KEYS and isinstance(normalized.get(output_key), list):
            normalized[output_key] = [
                _canonicalize_provider_value(entry)
                for entry in normalized.get(output_key) or []
            ]
        elif source_key in _PROVIDER_TEXT_KEYS:
            normalized[output_key] = _canonicalize_provider_text_from_contexts(
                normalized.get(output_key),
                provider_contexts,
            )

    if "provider_used" in normalized:
        normalized["provider_used"] = _public_provider_used(normalized.get("provider_used"))

    return normalized


def _build_step_result_payload(step: StepDefinition | None, result: StepResult) -> dict[str, Any]:
    provider_contexts = _merge_provider_contexts(
        result.provider_used,
        _provider_contexts_from_payload(result.outputs),
        _provider_contexts_from_captured_outputs(
            result.outputs if isinstance(result.outputs, Mapping) else {},
            dict(step.outputs_captured or {}) if step else {},
        ),
    )
    return {
        "step_id": result.step_id,
        "capability_id": step.capability_id if step else None,
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "outputs": _public_step_outputs(step, result.outputs, provider_used=result.provider_used),
        "cost_usd": result.cost_usd,
        "duration_ms": result.duration_ms,
        "receipt_id": result.receipt_id,
        "error": _canonicalize_provider_text_from_contexts(result.error, provider_contexts),
        "retries_used": result.retries_used,
        "provider_used": _public_provider_used(result.provider_used),
    }


def _terminal_outputs(recipe: RecipeDefinition, execution: RecipeExecution) -> dict[str, Any]:
    depended_on = {dep for step in recipe.steps for dep in step.depends_on}
    terminal_steps = [step for step in recipe.steps if step.step_id not in depended_on]
    outputs: dict[str, Any] = {}
    for step in terminal_steps:
        result = execution.step_results.get(step.step_id)
        if result and result.status == StepStatus.SUCCEEDED:
            outputs[step.step_id] = _public_step_outputs(step, result.outputs, provider_used=result.provider_used)
    return outputs


def _build_execution_payload(
    recipe: RecipeDefinition,
    execution: RecipeExecution,
    *,
    deduplicated: bool = False,
) -> dict[str, Any]:
    steps_by_id = {step.step_id: step for step in recipe.steps}
    provider_contexts: list[Any] = []
    for step_id, result in execution.step_results.items():
        step = steps_by_id.get(step_id)
        provider_contexts.extend(
            _merge_provider_contexts(
                result.provider_used,
                _provider_contexts_from_payload(result.outputs),
                _provider_contexts_from_captured_outputs(
                    result.outputs if isinstance(result.outputs, Mapping) else {},
                    dict(step.outputs_captured or {}) if step else {},
                ),
            )
        )
    return {
        "execution_id": execution.execution_id,
        "recipe_id": execution.recipe_id,
        "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        "total_cost_usd": execution.total_cost_usd,
        "total_duration_ms": execution.total_duration_ms,
        "started_at": _iso(execution.started_at),
        "completed_at": _iso(execution.completed_at),
        "error": _canonicalize_provider_text_from_contexts(execution.error, provider_contexts),
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
    steps_by_id = {step.step_id: step for step in recipe.steps}
    provider_contexts: list[Any] = []
    for row in step_rows:
        step = steps_by_id.get(str(row.get("step_id") or ""))
        provider_contexts.extend(
            _merge_provider_contexts(
                row.get("provider_used"),
                _provider_contexts_from_payload(row.get("outputs") or {}),
                _provider_contexts_from_captured_outputs(
                    row.get("outputs") if isinstance(row.get("outputs"), Mapping) else {},
                    dict(step.outputs_captured or {}) if step else {},
                ),
            )
        )
    step_results = [
        {
            "step_id": row.get("step_id"),
            "capability_id": row.get("capability_id"),
            "status": row.get("status"),
            "outputs": _public_step_outputs(
                steps_by_id.get(str(row.get("step_id") or "")),
                row.get("outputs") or {},
                provider_used=row.get("provider_used"),
            ),
            "cost_usd": row.get("cost_usd", 0.0),
            "duration_ms": row.get("duration_ms", 0),
            "receipt_id": row.get("receipt_id"),
            "error": _canonicalize_provider_text_from_contexts(
                row.get("error"),
                _merge_provider_contexts(
                    row.get("provider_used"),
                    _provider_contexts_from_payload(row.get("outputs") or {}),
                    _provider_contexts_from_captured_outputs(
                        row.get("outputs") if isinstance(row.get("outputs"), Mapping) else {},
                        dict(steps_by_id.get(str(row.get("step_id") or "")).outputs_captured or {})
                        if steps_by_id.get(str(row.get("step_id") or ""))
                        else {},
                    ),
                ),
            ),
            "retries_used": row.get("retries_used", 0),
            "provider_used": _public_provider_used(row.get("provider_used")),
        }
        for row in step_rows
    ]
    depended_on = {dep for step in recipe.steps for dep in step.depends_on}
    terminal_ids = {step.step_id for step in recipe.steps if step.step_id not in depended_on}
    outputs = {
        row.get("step_id"): _public_step_outputs(
            steps_by_id.get(str(row.get("step_id") or "")),
            row.get("outputs") or {},
            provider_used=row.get("provider_used"),
        )
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
        "error": _canonicalize_provider_text_from_contexts(execution_row.get("error"), provider_contexts),
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
        recipe_id: str,
        org_id: str,
        recipe_idempotency_key: str | None = None,
    ) -> None:
        self._raw_request = raw_request
        self._payload = payload
        self._safety_gate = safety_gate
        self._execution_id = execution_id
        self._recipe_id = recipe_id
        self._org_id = org_id
        self._recipe_idempotency_key = recipe_idempotency_key

    async def _check_aggregate_fanout_limits(self, step_id: str) -> str | None:
        limiter = await _get_recipe_step_rate_limiter()

        org_allowed, _org_remaining = await limiter.check_and_increment(
            f"recipe_fanout:org:{self._org_id}",
            _RECIPE_FANOUT_ORG_LIMIT,
            _RECIPE_FANOUT_WINDOW_SECONDS,
        )
        if not org_allowed:
            return (
                f"Aggregate recipe fan-out limit exceeded for organization {self._org_id} "
                f"while launching step '{step_id}'"
            )

        global_allowed, _global_remaining = await limiter.check_and_increment(
            "recipe_fanout:global",
            _RECIPE_FANOUT_GLOBAL_LIMIT,
            _RECIPE_FANOUT_WINDOW_SECONDS,
        )
        if not global_allowed:
            return f"Global recipe fan-out limit exceeded while launching step '{step_id}'"

        return None

    async def execute_step(
        self,
        step: StepDefinition,
        resolved_params: dict[str, Any],
        credential_mode: str = "rhumb_managed",
    ) -> StepResult:
        aggregate_limit_error = await self._check_aggregate_fanout_limits(step.step_id)
        if aggregate_limit_error is not None:
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=aggregate_limit_error,
            )

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
        step_idempotency_key = None
        if self._recipe_idempotency_key:
            step_idempotency_key = (
                f"recipe:{self._recipe_id}:{self._recipe_idempotency_key}:{step.step_id}"
            )

        response = await _forward_internal(
            self._raw_request,
            method="POST",
            path=f"/v2/capabilities/{step.capability_id}/execute",
            json_body={
                "parameters": resolved_params,
                "credential_mode": credential_mode,
                "interface": self._payload.interface,
                **({"idempotency_key": step_idempotency_key} if step_idempotency_key else {}),
                **({"policy": step_policy} if step_policy else {}),
            },
        )
        body = response.json() if hasattr(response, "json") else {}
        data = body.get("data") if isinstance(body, dict) else {}
        error = body.get("error") if isinstance(body, dict) else {}
        upstream_response = data.get("upstream_response") if isinstance(data, dict) else None
        root_outputs = {
            "result": _canonicalize_provider_payload(
                upstream_response if isinstance(upstream_response, dict) else (upstream_response or {}),
                provider_contexts=[
                    _public_provider_used(data.get("provider_used")) if isinstance(data, dict) else None,
                ],
            ),
            "provider_used": _public_provider_used(data.get("provider_used")) if isinstance(data, dict) else None,
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
        provider_contexts = _merge_provider_contexts(
            data.get("provider_used") if isinstance(data, dict) else None,
            _provider_contexts_from_payload(data),
            _provider_contexts_from_payload(error),
        )
        return StepResult(
            step_id=step.step_id,
            status=status,
            outputs={},
            cost_usd=float(data.get("cost_estimate_usd") or 0.0) if isinstance(data, dict) else 0.0,
            duration_ms=int(data.get("latency_ms") or 0) if isinstance(data, dict) else 0,
            receipt_id=str(data.get("receipt_id") or "") if isinstance(data, dict) else "",
            error=_canonicalize_provider_text_from_contexts(
                error_message or f"Capability execution failed with status {response.status_code}",
                provider_contexts,
            ),
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


async def _create_execution_placeholder(
    recipe: RecipeDefinition,
    *,
    execution_id: str,
    inputs: dict[str, Any],
    agent_id: str | None,
    org_id: str | None,
    credential_mode: str,
) -> None:
    await supabase_insert_required(
        "recipe_executions",
        {
            "execution_id": execution_id,
            "recipe_id": recipe.recipe_id,
            "status": "pending",
            "inputs": inputs,
            "total_cost_usd": 0.0,
            "total_duration_ms": 0,
            "step_count": len(recipe.steps),
            "steps_completed": 0,
            "error": None,
            "started_at": None,
            "completed_at": None,
            "org_id": org_id,
            "agent_id": agent_id,
            "credential_mode": credential_mode,
        },
    )


async def _persist_execution(
    recipe: RecipeDefinition,
    execution: RecipeExecution,
    *,
    inputs: dict[str, Any],
    agent_id: str | None,
    org_id: str | None,
    credential_mode: str,
) -> None:
    provider_contexts: list[Any] = []
    steps_by_id = {step.step_id: step for step in recipe.steps}
    for step_id, result in execution.step_results.items():
        step = steps_by_id.get(step_id)
        provider_contexts.extend(
            _merge_provider_contexts(
                result.provider_used,
                _provider_contexts_from_payload(result.outputs),
                _provider_contexts_from_captured_outputs(
                    result.outputs if isinstance(result.outputs, Mapping) else {},
                    dict(step.outputs_captured or {}) if step else {},
                ),
            )
        )
    await supabase_patch_required(
        f"recipe_executions?execution_id=eq.{quote(execution.execution_id)}",
        {
            "recipe_id": recipe.recipe_id,
            "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
            "inputs": inputs,
            "total_cost_usd": execution.total_cost_usd,
            "total_duration_ms": execution.total_duration_ms,
            "step_count": len(recipe.steps),
            "steps_completed": sum(1 for result in execution.step_results.values() if result.status == StepStatus.SUCCEEDED),
            "error": _canonicalize_provider_text_from_contexts(execution.error, provider_contexts),
            "started_at": execution.started_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "org_id": org_id,
            "agent_id": agent_id,
            "credential_mode": credential_mode,
        },
    )

    for step_id, result in execution.step_results.items():
        step = steps_by_id.get(step_id)
        step_provider_contexts = _merge_provider_contexts(
            result.provider_used,
            _provider_contexts_from_payload(result.outputs),
            _provider_contexts_from_captured_outputs(
                result.outputs if isinstance(result.outputs, Mapping) else {},
                dict(step.outputs_captured or {}) if step else {},
            ),
        )
        await supabase_insert_required(
            "recipe_step_executions",
            {
                "execution_id": execution.execution_id,
                "step_id": step_id,
                "capability_id": step.capability_id if step else "",
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
                "receipt_id": result.receipt_id or None,
                "provider_used": _public_provider_used(result.provider_used),
                "retries_used": result.retries_used,
                "error": _canonicalize_provider_text_from_contexts(result.error, step_provider_contexts),
                "outputs": _public_step_outputs(step, result.outputs, provider_used=result.provider_used),
                "started_at": execution.started_at.isoformat(),
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            },
        )


@router.get("/recipes")
async def list_recipes(
    category: str | None = Query(default=None, description="Filter by recipe category"),
    stability: str | None = Query(default=None, description="Filter by recipe stability (stable, beta, all)"),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
) -> JSONResponse:
    limit = _validated_recipe_list_limit(limit)
    offset = _validated_recipe_list_offset(offset)
    normalized_stability = _validated_recipe_stability_filter(stability)
    requested_category = _validated_recipe_category_before_reads(category)
    normalized_category = None
    if requested_category is not None:
        normalized_category = _validated_recipe_category(
            requested_category,
            available_categories=await _available_recipe_categories(),
        )

    query = (
        "recipes"
        "?select=recipe_id,name,version,category,stability,tier,step_count,max_total_cost_usd,published,updated_at"
        "&published=eq.true"
        "&order=updated_at.desc.nullslast,recipe_id.asc"
        f"&limit={limit}&offset={offset}"
    )
    if normalized_category:
        query += f"&category=eq.{quote(normalized_category)}"
    if normalized_stability:
        query += f"&stability=eq.{quote(normalized_stability)}"

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
            message="Recipe execution requires a valid governed API key.",
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

    outbox_health = get_event_outbox_health()
    if not outbox_health.allows_risky_writes:
        raise RhumbError(
            "EXECUTION_DISABLED",
            message="Recipe execution is temporarily blocked because billing/audit durability is unavailable.",
            detail=outbox_health.reason or "Retry after the durable event outbox recovers.",
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
        idempotency_key=None,
    )

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

    durable_idempotency = None
    if effective_idempotency_key:
        try:
            durable_idempotency = await _get_idempotency_store()
            existing_claim = await durable_idempotency.claim(
                effective_idempotency_key,
                execution_id,
                recipe.recipe_id,
                org_id=agent.organization_id,
                agent_id=agent.agent_id,
                allow_fallback=False,
            )
        except IdempotencyUnavailable as exc:
            raise RhumbError(
                "EXECUTION_DISABLED",
                message="Recipe idempotency protection is temporarily unavailable.",
                detail="Retry shortly after control-plane durability recovers.",
            ) from exc

        if existing_claim is not None:
            execution_row, step_rows = await _fetch_execution_rows(existing_claim.execution_id)
            if execution_row is not None:
                replay_payload = _build_execution_payload_from_rows(
                    recipe,
                    execution_row,
                    step_rows,
                    deduplicated=True,
                )
            else:
                replay_payload = {
                    "execution_id": existing_claim.execution_id,
                    "recipe_id": existing_claim.recipe_id,
                    "status": existing_claim.status,
                    "deduplicated": True,
                    "layer": _LAYER,
                    "outputs": {},
                    "step_results": [],
                    "receipt_chain_hash": existing_claim.result_hash,
                }
            return _json_response(200, {"data": replay_payload, "error": None})

    try:
        await _create_execution_placeholder(
            recipe,
            execution_id=execution_id,
            inputs=payload.inputs,
            agent_id=agent.agent_id,
            org_id=agent.organization_id,
            credential_mode=payload.credential_mode,
        )
    except SupabaseWriteUnavailable as exc:
        raise RhumbError(
            "EXECUTION_DISABLED",
            message="Recipe execution control plane is temporarily unavailable.",
            detail="Retry shortly after durable execution recording recovers.",
        ) from exc

    engine = RecipeEngine(
        step_executor=_InternalRecipeStepExecutor(
            raw_request=raw_request,
            payload=payload,
            safety_gate=safety_gate,
            execution_id=execution_id,
            recipe_id=recipe.recipe_id,
            org_id=agent.organization_id,
            recipe_idempotency_key=effective_idempotency_key,
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

    try:
        await _persist_execution(
            recipe,
            execution,
            inputs=payload.inputs,
            agent_id=agent.agent_id,
            org_id=agent.organization_id,
            credential_mode=payload.credential_mode,
        )
    except SupabaseWriteUnavailable as exc:
        raise RhumbError(
            "EXECUTION_DISABLED",
            message="Recipe execution could not be durably recorded.",
            detail="Execution may have run, but persistence is unavailable; do not assume replay safety until control-plane durability recovers.",
        ) from exc

    safety_gate.finalize_execution(
        chain_id=execution_id,
        execution_id=execution_id,
        idempotency_key=None,
        recipe_id=recipe.recipe_id,
        status=execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        result_hash=execution.receipt_chain_hash,
    )

    if effective_idempotency_key and durable_idempotency is not None:
        await durable_idempotency.store(
            effective_idempotency_key,
            execution_id,
            recipe.recipe_id,
            execution.status.value if hasattr(execution.status, "value") else str(execution.status),
            execution.receipt_chain_hash,
        )

    response_payload = _build_execution_payload(recipe, execution)
    return _json_response(
        _status_code_for_recipe(response_payload["status"]),
        {"data": response_payload, "error": None},
    )
