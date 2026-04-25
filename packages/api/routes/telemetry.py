"""Telemetry read APIs over capability execution logs."""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from routes._supabase import supabase_fetch
from schemas.agent_identity import get_agent_identity_store
from services.error_envelope import RhumbError
from services.service_slugs import CANONICAL_TO_PROXY, public_service_slug, public_service_slug_candidates

router = APIRouter()

_SELECT_FIELDS = (
    "id,agent_id,capability_id,provider_used,credential_mode,method,path,"
    "upstream_status,success,cost_estimate_usd,cost_usd_cents,upstream_cost_cents,"
    "margin_cents,total_latency_ms,upstream_latency_ms,billing_status,"
    "fallback_attempted,fallback_provider,interface,error_message,executed_at"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _public_provider_slug(value: Any) -> str | None:
    return public_service_slug(value)


def _validated_optional_filter(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if normalized:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message=f"Invalid '{field_name}' filter.",
        detail=f"Provide a non-empty {field_name} value or omit the filter.",
    )


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


def _canonicalize_provider_text(text: Any, provider_slug: Any) -> str | None:
    if text is None:
        return None

    canonical = _public_provider_slug(provider_slug)
    if canonical is None:
        return str(text)

    raw_provider_slug = str(provider_slug).strip().lower() if provider_slug else None
    if raw_provider_slug == canonical.lower():
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
    return _canonicalize_known_provider_aliases(canonicalized)


def _canonicalize_provider_text_from_contexts(text: Any, provider_values: list[Any]) -> str | None:
    if text is None:
        return None

    canonicalized = str(text)
    seen: set[str] = set()
    for provider_value in provider_values:
        provider_key = str(provider_value or "").strip()
        if not provider_key:
            continue
        lowered = provider_key.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        canonicalized = _canonicalize_provider_text(canonicalized, provider_key) or canonicalized
    return _canonicalize_known_provider_aliases(canonicalized)


def _status_key(value: Any) -> str | None:
    status = _to_int(value)
    return str(status) if status is not None else None


def _cost_usd(row: dict[str, Any]) -> float:
    cost_cents = _to_int(row.get("cost_usd_cents"))
    if cost_cents is not None:
        return round(cost_cents / 100.0, 4)
    estimate = _to_float(row.get("cost_estimate_usd"))
    return round(estimate, 4) if estimate is not None else 0.0


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[rank], 1)


def _success_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    successes = sum(1 for row in rows if _to_bool(row.get("success")))
    return round(successes / len(rows), 3)


def _provider_status(success_rate: float, total_calls: int) -> str:
    if total_calls == 0:
        return "unknown"
    if success_rate >= 0.95:
        return "healthy"
    if success_rate >= 0.80:
        return "degraded"
    return "unhealthy"


class _TelemetryAuthError(RuntimeError):
    """Raised when telemetry auth fails and a route-level envelope is needed."""


def _error_response(
    request: Request,
    *,
    status_code: int,
    error: str,
    message: str,
    resolution: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "message": message,
            "resolution": resolution,
            "request_id": request_id,
        },
    )


async def _require_agent(
    x_rhumb_key: str | None,
) -> tuple[str, str]:
    if not x_rhumb_key:
        raise _TelemetryAuthError("Missing X-Rhumb-Key header")

    identity_store = get_agent_identity_store()
    agent = await identity_store.verify_api_key_with_agent(x_rhumb_key)
    if agent is None:
        raise _TelemetryAuthError("Invalid or expired governed API key")

    return agent.agent_id, agent.organization_id


def _row_timestamp_value(row: dict[str, Any]) -> str | None:
    value = row.get("executed_at")
    if isinstance(value, str) and value:
        return value
    legacy_value = row.get("created_at")
    return legacy_value if isinstance(legacy_value, str) and legacy_value else None


def _row_timestamp(row: dict[str, Any]) -> datetime | None:
    return _parse_timestamp(_row_timestamp_value(row))


def _build_usage_query(
    *,
    start_at: datetime | None = None,
    agent_id: str | None = None,
    capability_id: str | None = None,
    provider: str | None = None,
    success: bool | None = None,
    limit: int | None = None,
) -> str:
    params = [f"select={_SELECT_FIELDS}"]
    if agent_id:
        params.append(f"agent_id=eq.{quote(agent_id, safe='')}")
    if capability_id:
        params.append(f"capability_id=eq.{quote(capability_id, safe='')}")
    provider_candidates = public_service_slug_candidates(provider)
    if provider_candidates:
        if len(provider_candidates) == 1:
            params.append(f"provider_used=eq.{quote(provider_candidates[0], safe='')}")
        else:
            provider_filters = ",".join(
                f"provider_used.eq.{quote(candidate, safe='')}"
                for candidate in provider_candidates
            )
            params.append(f"or=({provider_filters})")
    if success is not None:
        params.append(f"success=eq.{str(success).lower()}")
    if start_at is not None:
        params.append(f"executed_at=gte.{quote(_to_iso8601(start_at), safe='')}")
    params.append("order=executed_at.desc")
    if limit is not None:
        params.append(f"limit={limit}")
    return "capability_executions?" + "&".join(params)


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    start_at: datetime | None = None,
    capability_id: str | None = None,
    provider: str | None = None,
    success: bool | None = None,
) -> list[dict[str, Any]]:
    provider_slug = _public_provider_slug(provider)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if capability_id and row.get("capability_id") != capability_id:
            continue
        if provider_slug and _public_provider_slug(row.get("provider_used")) != provider_slug:
            continue
        if success is not None and _to_bool(row.get("success")) != success:
            continue
        timestamp = _row_timestamp(row)
        if start_at is not None and (timestamp is None or timestamp < start_at):
            continue
        filtered.append(row)

    filtered.sort(
        key=lambda row: _row_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return filtered


def _build_summary(agent_id: str, rows: list[dict[str, Any]], period_days: int) -> dict[str, Any]:
    latencies = [_to_float(row.get("total_latency_ms")) for row in rows]
    latency_values = [latency for latency in latencies if latency is not None]
    total_calls = len(rows)
    successful_calls = sum(1 for row in rows if _to_bool(row.get("success")))

    return {
        "agent_id": agent_id,
        "period_days": period_days,
        "summary": {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": total_calls - successful_calls,
            "total_cost_usd": round(sum(_cost_usd(row) for row in rows), 4),
            "avg_latency_ms": _average(latency_values),
            "p50_latency_ms": _percentile(latency_values, 0.50),
            "p95_latency_ms": _percentile(latency_values, 0.95),
        },
    }


def _group_by_capability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("capability_id") or "unknown"].append(row)

    items: list[dict[str, Any]] = []
    for capability_id, group in grouped.items():
        provider_counts = Counter(
            _public_provider_slug(row.get("provider_used")) or "unknown"
            for row in group
        )
        latencies = [_to_float(row.get("total_latency_ms")) for row in group]
        latency_values = [latency for latency in latencies if latency is not None]
        top_provider = None
        if provider_counts:
            top_provider = sorted(provider_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

        items.append(
            {
                "capability_id": capability_id,
                "calls": len(group),
                "success_rate": _success_rate(group),
                "avg_latency_ms": _average(latency_values),
                "total_cost_usd": round(sum(_cost_usd(row) for row in group), 4),
                "top_provider": top_provider,
            }
        )

    return sorted(items, key=lambda item: (-item["calls"], item["capability_id"]))


def _group_by_provider(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_public_provider_slug(row.get("provider_used")) or "unknown"].append(row)

    items: list[dict[str, Any]] = []
    for provider, group in grouped.items():
        total_calls = len(group)
        success_rate = _success_rate(group)
        total_latencies = [_to_float(row.get("total_latency_ms")) for row in group]
        upstream_latencies = [_to_float(row.get("upstream_latency_ms")) for row in group]
        total_latency_values = [latency for latency in total_latencies if latency is not None]
        upstream_latency_values = [latency for latency in upstream_latencies if latency is not None]
        items.append(
            {
                "provider": provider,
                "calls": total_calls,
                "success_rate": success_rate,
                "avg_latency_ms": _average(total_latency_values),
                "total_cost_usd": round(sum(_cost_usd(row) for row in group), 4),
                "error_rate": round(1 - success_rate, 3),
                "avg_upstream_latency_ms": _average(upstream_latency_values),
            }
        )

    return sorted(items, key=lambda item: (-item["calls"], item["provider"]))


def _group_by_time(
    rows: list[dict[str, Any]],
    granularity: Literal["day", "hour"],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        timestamp = _row_timestamp(row)
        if timestamp is None:
            continue
        bucket = timestamp.strftime("%Y-%m-%d") if granularity == "day" else timestamp.strftime("%Y-%m-%dT%H:00:00Z")
        grouped[bucket].append(row)

    items: list[dict[str, Any]] = []
    for period, group in grouped.items():
        latencies = [_to_float(row.get("total_latency_ms")) for row in group]
        latency_values = [latency for latency in latencies if latency is not None]
        items.append(
            {
                "period": period,
                "calls": len(group),
                "success_rate": _success_rate(group),
                "avg_latency_ms": _average(latency_values),
            }
        )

    return sorted(items, key=lambda item: item["period"])


def _health_rows_to_payload(provider: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [_to_float(row.get("total_latency_ms")) for row in rows]
    latency_values = [latency for latency in latencies if latency is not None]
    success_rate = _success_rate(rows)
    last_seen_value = None
    if rows:
        parsed_timestamps = [_row_timestamp(row) for row in rows]
        timestamps = [timestamp for timestamp in parsed_timestamps if timestamp is not None]
        if timestamps:
            last_seen_value = _to_iso8601(max(timestamps))

    error_distribution: dict[str, int] = {}
    if rows:
        counter = Counter()
        for row in rows:
            if _to_bool(row.get("success")):
                continue
            status_key = _status_key(row.get("upstream_status"))
            if status_key:
                counter[status_key] += 1
        error_distribution = dict(sorted(counter.items(), key=lambda item: item[0]))

    return {
        "provider": provider,
        "total_calls": len(rows),
        "success_rate": success_rate,
        "avg_latency_ms": _average(latency_values),
        "p95_latency_ms": _percentile(latency_values, 0.95),
        "error_distribution": error_distribution,
        "status": _provider_status(success_rate, len(rows)),
        "last_seen": last_seen_value,
    }


@router.get("/telemetry/usage")
async def get_usage_telemetry(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Lookback window in days."),
    capability_id: str | None = Query(None, description="Filter to a capability ID."),
    provider: str | None = Query(None, description="Filter to a provider."),
    group_by: Literal["capability", "provider", "day", "hour"] | None = Query(
        None,
        description="Primary aggregation axis.",
    ),
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Return per-agent usage analytics from execution logs."""
    try:
        agent_id, _org_id = await _require_agent(x_rhumb_key)
    except _TelemetryAuthError as exc:
        return _error_response(
            request,
            status_code=401,
            error="unauthorized",
            message=str(exc),
            resolution="Provide a valid governed API key via X-Rhumb-Key header.",
        )
    capability_id = _validated_optional_filter(capability_id, field_name="capability_id")
    provider = _validated_optional_filter(provider, field_name="provider")
    start_at = _utcnow() - timedelta(days=days)
    rows = await supabase_fetch(
        _build_usage_query(
            start_at=start_at,
            agent_id=agent_id,
            capability_id=capability_id,
            provider=provider,
            limit=10000,
        )
    )
    filtered_rows = _filter_rows(
        rows or [],
        start_at=start_at,
        capability_id=capability_id,
        provider=provider,
    )
    time_granularity: Literal["day", "hour"] = "hour" if group_by == "hour" else "day"

    payload = _build_summary(agent_id, filtered_rows, days)
    payload["by_capability"] = _group_by_capability(filtered_rows)
    payload["by_provider"] = _group_by_provider(filtered_rows)
    payload["by_time"] = _group_by_time(filtered_rows, time_granularity)

    return {"data": payload, "error": None}


@router.get("/telemetry/provider-health")
async def get_provider_health(
    provider: str | None = Query(None, description="Filter to one provider."),
    hours: int = Query(24, ge=1, le=168, description="Lookback window in hours."),
) -> dict[str, Any]:
    """Return aggregate provider health from execution telemetry."""
    provider = _validated_optional_filter(provider, field_name="provider")
    start_at = _utcnow() - timedelta(hours=hours)
    rows = await supabase_fetch(
        _build_usage_query(
            start_at=start_at,
            provider=provider,
            limit=10000,
        )
    )
    filtered_rows = _filter_rows(rows or [], start_at=start_at, provider=provider)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in filtered_rows:
        grouped[_public_provider_slug(row.get("provider_used")) or "unknown"].append(row)

    providers = [
        _health_rows_to_payload(provider_name, group_rows)
        for provider_name, group_rows in grouped.items()
    ]
    providers.sort(key=lambda item: (-item["total_calls"], item["provider"]))

    if provider and not providers:
        providers = [_health_rows_to_payload(_public_provider_slug(provider) or provider, [])]

    return {
        "data": {
            "window_hours": hours,
            "providers": providers,
        },
        "error": None,
    }


@router.get("/telemetry/recent")
async def get_recent_executions(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of recent executions."),
    capability_id: str | None = Query(None, description="Filter to a capability ID."),
    success: bool | None = Query(None, description="Filter by success/failure."),
    x_rhumb_key: str | None = Header(None, alias="X-Rhumb-Key"),
) -> dict[str, Any]:
    """Return recent execution records for the authenticated agent."""
    try:
        agent_id, _org_id = await _require_agent(x_rhumb_key)
    except _TelemetryAuthError as exc:
        return _error_response(
            request,
            status_code=401,
            error="unauthorized",
            message=str(exc),
            resolution="Provide a valid governed API key via X-Rhumb-Key header.",
        )
    capability_id = _validated_optional_filter(capability_id, field_name="capability_id")
    rows = await supabase_fetch(
        _build_usage_query(
            agent_id=agent_id,
            capability_id=capability_id,
            success=success,
            limit=limit,
        )
    )
    filtered_rows = _filter_rows(
        rows or [],
        capability_id=capability_id,
        success=success,
    )[:limit]

    records = [
        {
            "id": row.get("id"),
            "agent_id": row.get("agent_id"),
            "capability_id": row.get("capability_id"),
            "provider_used": _public_provider_slug(row.get("provider_used")),
            "credential_mode": row.get("credential_mode"),
            "method": row.get("method"),
            "path": row.get("path"),
            "upstream_status": _to_int(row.get("upstream_status")),
            "success": _to_bool(row.get("success")),
            "cost_estimate_usd": _to_float(row.get("cost_estimate_usd")),
            "cost_usd_cents": _to_int(row.get("cost_usd_cents")),
            "upstream_cost_cents": _to_int(row.get("upstream_cost_cents")),
            "margin_cents": _to_int(row.get("margin_cents")),
            "total_latency_ms": _to_float(row.get("total_latency_ms")),
            "upstream_latency_ms": _to_float(row.get("upstream_latency_ms")),
            "billing_status": row.get("billing_status"),
            "fallback_attempted": _to_bool(row.get("fallback_attempted")),
            "fallback_provider": _public_provider_slug(row.get("fallback_provider")),
            "interface": row.get("interface"),
            "error_message": _canonicalize_provider_text_from_contexts(
                row.get("error_message"),
                [row.get("provider_used"), row.get("fallback_provider")],
            ),
            "executed_at": _row_timestamp_value(row),
            "created_at": _row_timestamp_value(row),
        }
        for row in filtered_rows
    ]

    return {"data": records, "error": None}
