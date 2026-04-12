"""Aggregation helpers for the internal launch dashboard."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from services.payload_redactor import sanitize_external_payload

LAUNCH_WINDOW_START = datetime(2026, 3, 13, tzinfo=UTC)
SUPPORTED_WINDOWS = {"24h", "7d", "launch"}


def resolve_window_start(window: str, *, now: datetime) -> datetime:
    """Resolve the start timestamp for a supported dashboard window."""
    if window == "24h":
        return now - timedelta(hours=24)
    if window == "7d":
        return now - timedelta(days=7)
    if window == "launch":
        return LAUNCH_WINDOW_START
    raise ValueError(f"Unsupported window: {window}")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _top_counts(counter: Counter[str], *, limit: int = 5) -> list[dict[str, Any]]:
    return [
        {"key": key, "count": count}
        for key, count in counter.most_common(limit)
    ]


def _normalize_service_slug(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _safe_label(value: Any, *, max_length: int = 120) -> str | None:
    sanitized = sanitize_external_payload(
        value,
        max_depth=1,
        max_items=5,
        max_string_length=max_length,
        strict=True,
    )
    if isinstance(sanitized, str) and sanitized:
        return sanitized
    return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _execution_period(created_at: datetime, *, window: str) -> str:
    if window == "24h":
        return created_at.strftime("%Y-%m-%dT%H:00:00Z")
    return created_at.strftime("%Y-%m-%d")


def _normalize_credential_mode(value: Any) -> str:
    mode = _safe_label(value, max_length=40)
    if not mode:
        return "unknown"

    normalized = mode.lower()
    if normalized in {"byo", "byok"}:
        return "byok"
    return normalized


def _client_key(row: dict[str, Any]) -> str | None:
    agent_id = _safe_label(row.get("agent_id"))
    if agent_id:
        return f"agent:{agent_id}"

    user_agent = _safe_label(row.get("user_agent"))
    if user_agent:
        return f"ua:{user_agent}"

    return None


def _execution_caller_key(row: dict[str, Any]) -> str | None:
    agent_id = _safe_label(row.get("agent_id"))
    if agent_id:
        return f"agent:{agent_id}"

    interface = _safe_label(row.get("interface"), max_length=40)
    if interface:
        return f"interface:{interface}"

    return None


def _build_funnel_transition(from_stage: str, to_stage: str, *, from_count: int, to_count: int) -> dict[str, Any]:
    progressed_count = min(from_count, to_count)
    dropoff_count = max(from_count - to_count, 0)
    overflow_count = max(to_count - from_count, 0)
    return {
        "from_stage": from_stage,
        "to_stage": to_stage,
        "from_count": from_count,
        "to_count": to_count,
        "progressed_count": progressed_count,
        "dropoff_count": dropoff_count,
        "dropoff_rate": round(dropoff_count / from_count, 4) if from_count else None,
        "conversion_rate": round(progressed_count / from_count, 4) if from_count else None,
        "overflow_count": overflow_count,
    }


def _build_readiness_signal(
    key: str,
    label: str,
    *,
    value: int | float | None,
    target: int | float | None,
    met: bool | None,
    detail: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "target": target,
        "met": met,
        "detail": detail,
    }


def _launch_focus_from_dropoff(biggest_dropoff: dict[str, Any] | None) -> str:
    if not biggest_dropoff:
        return "Keep watching real traffic. There is not enough funnel evidence yet to call the next bottleneck."

    from_stage = biggest_dropoff.get("from_stage")
    to_stage = biggest_dropoff.get("to_stage")
    if from_stage == "queries" and to_stage == "service_views":
        return (
            "Sharpen the query-to-service handoff. Ranking, snippet clarity, or the first landing page may still be hiding the right next step."
        )
    if from_stage == "service_views" and to_stage == "provider_clicks":
        return (
            "Tighten service-page trust and CTA clarity. People are viewing services but not moving deeper, so proof or positioning is still weak."
        )
    if from_stage == "provider_clicks" and to_stage == "execute_attempts":
        return (
            "Reduce the resolve/setup gap. People show intent after viewing providers, but the path into execute still has credential or onboarding friction."
        )
    if from_stage == "execute_attempts" and to_stage == "successful_executes":
        return (
            "Focus on first-run reliability and setup success. The demand signal exists, but successful execution is still the bottleneck."
        )
    return "Keep watching the live path and tighten the stage with the biggest visible drop-off."


def _build_launch_readiness(
    *,
    unique_execution_callers: int,
    successful_executions: int,
    repeat_execution_callers: int,
    first_time_execution_attempts: int,
    first_time_execution_successes: int,
    managed_attempts: int,
    managed_first_success_callers: int,
    first_success_callers: int,
    biggest_dropoff: dict[str, Any] | None,
) -> dict[str, Any]:
    minimum_unique_callers = 3
    minimum_successful_executes = 5
    minimum_repeat_callers = 1
    minimum_first_time_success_rate = 0.5
    minimum_managed_first_success_share = 0.5

    first_time_success_rate = (
        round(first_time_execution_successes / first_time_execution_attempts, 4)
        if first_time_execution_attempts
        else None
    )
    managed_first_success_share = (
        round(managed_first_success_callers / first_success_callers, 4)
        if first_success_callers
        else None
    )
    biggest_dropoff_rate = biggest_dropoff.get("dropoff_rate") if biggest_dropoff else None

    signals = [
        _build_readiness_signal(
            "successful_executes",
            "Successful executes",
            value=successful_executions,
            target=minimum_successful_executes,
            met=successful_executions >= minimum_successful_executes,
            detail="Need enough successful execution volume in-window before a launch-readiness call is credible.",
        ),
        _build_readiness_signal(
            "unique_callers",
            "Unique execution callers",
            value=unique_execution_callers,
            target=minimum_unique_callers,
            met=unique_execution_callers >= minimum_unique_callers,
            detail="A small-group recommendation needs signal from more than one or two isolated operators.",
        ),
        _build_readiness_signal(
            "repeat_callers",
            "Repeat callers",
            value=repeat_execution_callers,
            target=minimum_repeat_callers,
            met=repeat_execution_callers >= minimum_repeat_callers,
            detail="Repeat usage is the first proof that Rhumb is becoming part of a real workflow instead of a one-off test.",
        ),
        _build_readiness_signal(
            "first_time_success_rate",
            "Window-first success rate",
            value=first_time_success_rate,
            target=minimum_first_time_success_rate,
            met=(
                first_time_success_rate >= minimum_first_time_success_rate
                if first_time_success_rate is not None
                else None
            ),
            detail="If first-use success is weak, the remaining blocker is still onboarding or product friction rather than lack of traffic alone.",
        ),
        _build_readiness_signal(
            "managed_first_success_share",
            "Managed first-success share",
            value=managed_first_success_share,
            target=minimum_managed_first_success_share,
            met=(
                managed_first_success_share >= minimum_managed_first_success_share
                if managed_first_success_share is not None
                else False
            ),
            detail="Low-heroics launch readiness means the Rhumb-managed path should win a meaningful share of first successes.",
        ),
    ]

    if (
        successful_executions < minimum_successful_executes
        or unique_execution_callers < minimum_unique_callers
    ):
        status = "insufficient_signal"
        headline = "Not enough live usage signal yet to call small-group readiness."
        summary = (
            "Some launch traffic is landing, but the sample is still too thin to separate product truth from noise."
        )
    elif (
        first_time_success_rate is not None and first_time_success_rate < minimum_first_time_success_rate
    ) or (
        biggest_dropoff
        and biggest_dropoff.get("from_stage") in {"provider_clicks", "execute_attempts"}
        and isinstance(biggest_dropoff_rate, float)
        and biggest_dropoff_rate >= 0.5
    ):
        status = "onboarding_friction"
        headline = "Launch traffic exists, but onboarding friction is still the blocker."
        summary = (
            "The current window shows intent, but too many new users are falling out before first success or at the execution step."
        )
    elif repeat_execution_callers < minimum_repeat_callers:
        status = "repeat_usage_gap"
        headline = "First-use signal exists, but repeat usage is not proven yet."
        summary = (
            "Rhumb is getting through first contact, but the window still lacks evidence that operators come back for a second real workflow."
        )
    elif managed_first_success_share is None or managed_first_success_share < minimum_managed_first_success_share:
        status = "managed_path_gap"
        headline = "Usage exists, but the low-heroics managed path is not winning first success yet."
        summary = (
            "The product may be usable, but launch readiness is still capped if early wins depend mostly on bridge-heavy setup instead of Rhumb-managed superpowers."
        )
    else:
        status = "small_group_candidate"
        headline = "The current window looks strong enough to prepare a small-group-ready recommendation."
        summary = (
            "Signal quality is now broad enough to move from telemetry watching into a concrete go or not-yet recommendation for a bounded small group."
        )

    return {
        "status": status,
        "headline": headline,
        "summary": summary,
        "next_focus": _launch_focus_from_dropoff(biggest_dropoff),
        "signals": signals,
    }


def build_launch_dashboard(
    *,
    query_logs: Iterable[dict[str, Any]],
    click_events: Iterable[dict[str, Any]],
    execution_rows: Iterable[dict[str, Any]],
    service_rows: Iterable[dict[str, Any]],
    window: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build dashboard metrics from recent query logs and click events."""
    now_utc = (now or datetime.now(tz=UTC)).astimezone(UTC)
    start_at = resolve_window_start(window, now=now_utc)

    query_rows = []
    for row in query_logs:
        created_at = _parse_timestamp(row.get("created_at"))
        if created_at is None or created_at < start_at:
            continue
        query_rows.append({**row, "_created_at": created_at})

    click_rows = []
    for row in click_events:
        created_at = _parse_timestamp(row.get("created_at"))
        if created_at is None or created_at < start_at:
            continue
        click_rows.append({**row, "_created_at": created_at})

    filtered_execution_rows = []
    for row in execution_rows:
        executed_at = _parse_timestamp(row.get("executed_at"))
        if executed_at is None or executed_at < start_at:
            continue
        filtered_execution_rows.append({**row, "_executed_at": executed_at})

    by_source = Counter[str]()
    by_query_type = Counter[str]()
    top_services = Counter[str]()
    top_searches = Counter[str]()
    client_counts = Counter[str]()
    repeat_clients = 0

    for row in query_rows:
        source = str(row.get("source") or "unknown")
        by_source[source] += 1

        query_type = str(row.get("query_type") or "unknown")
        by_query_type[query_type] += 1

        if query_type == "score_lookup":
            service_slug = _normalize_service_slug(
                (row.get("query_params") or {}).get("slug")
                if isinstance(row.get("query_params"), dict)
                else None
            ) or _normalize_service_slug(row.get("query_text"))
            if service_slug:
                top_services[service_slug] += 1

        if query_type == "search":
            query_text = _safe_label(row.get("query_text"))
            if query_text:
                top_searches[query_text] += 1

        client_key = _client_key(row)
        if client_key:
            client_counts[client_key] += 1

    repeat_clients = sum(1 for count in client_counts.values() if count > 1)
    unique_clients = len(client_counts)

    provider_clicks = Counter[str]()
    provider_clicks_by_service = Counter[str]()
    dispute_clicks_by_type = Counter[str]()
    clicks_by_surface = Counter[str]()
    top_capabilities = Counter[str]()
    execution_callers = Counter[str]()
    executions_by_interface = Counter[str]()
    executions_by_credential_mode = Counter[str]()
    successful_executions_by_credential_mode = Counter[str]()
    first_success_modes = Counter[str]()
    success_trend: dict[str, dict[str, Any]] = {}
    successful_executions = 0
    first_time_execution_attempts = 0
    first_time_execution_successes = 0
    repeat_execution_attempts = 0
    repeat_execution_successes = 0
    unattributed_execution_attempts = 0
    unattributed_execution_successes = 0
    caller_first_success_mode: dict[str, str] = {}

    for row in click_rows:
        event_type = str(row.get("event_type") or "unknown")
        surface = str(row.get("source_surface") or "unknown")
        clicks_by_surface[surface] += 1

        if event_type == "provider_click":
            domain = str(row.get("destination_domain") or row.get("service_slug") or "unknown")
            provider_clicks[domain] += 1
            service_slug = _normalize_service_slug(row.get("service_slug"))
            if service_slug:
                provider_clicks_by_service[service_slug] += 1

        if event_type in {"dispute_click", "github_dispute_click", "contact_click"}:
            dispute_clicks_by_type[event_type] += 1

    execution_caller_attempts = Counter[str]()
    for row in sorted(filtered_execution_rows, key=lambda row: row["_executed_at"]):
        capability_id = _safe_label(row.get("capability_id"), max_length=80) or "unknown"
        top_capabilities[capability_id] += 1

        credential_mode = _normalize_credential_mode(row.get("credential_mode"))
        executions_by_credential_mode[credential_mode] += 1

        caller_key = _execution_caller_key(row)
        if caller_key:
            execution_callers[caller_key] += 1

        interface = _safe_label(row.get("interface"), max_length=40) or "unknown"
        executions_by_interface[interface] += 1

        period = _execution_period(row["_executed_at"], window=window)
        bucket = success_trend.setdefault(
            period,
            {"period": period, "total": 0, "successful": 0, "failed": 0},
        )
        bucket["total"] += 1

        success = _to_bool(row.get("success"))
        if success:
            successful_executions += 1
            bucket["successful"] += 1
            successful_executions_by_credential_mode[credential_mode] += 1
            if caller_key and caller_key not in caller_first_success_mode:
                caller_first_success_mode[caller_key] = credential_mode
        else:
            bucket["failed"] += 1

        if caller_key is None:
            unattributed_execution_attempts += 1
            if success:
                unattributed_execution_successes += 1
            continue

        if execution_caller_attempts[caller_key] == 0:
            first_time_execution_attempts += 1
            if success:
                first_time_execution_successes += 1
        else:
            repeat_execution_attempts += 1
            if success:
                repeat_execution_successes += 1

        execution_caller_attempts[caller_key] += 1

    service_views = Counter[str]()
    for row in query_rows:
        if row.get("query_type") != "score_lookup":
            continue
        service_slug = _normalize_service_slug(
            (row.get("query_params") or {}).get("slug")
            if isinstance(row.get("query_params"), dict)
            else None
        ) or _normalize_service_slug(row.get("query_text"))
        if service_slug:
            service_views[service_slug] += 1

    ctr_rows = []
    for service_slug, clicks in provider_clicks_by_service.items():
        views = service_views.get(service_slug, 0)
        ctr_rows.append({
            "service_slug": service_slug,
            "clicks": clicks,
            "views": views,
            "ctr": round(clicks / views, 4) if views > 0 else None,
        })
    ctr_rows.sort(
        key=lambda row: (
            row["ctr"] is None,
            -(row["ctr"] or 0.0),
            -row["clicks"],
            row["service_slug"],
        )
    )

    machine_queries = sum(
        count for source, count in by_source.items() if source in {"api_direct", "cli", "mcp", "unknown_agent"}
    )
    failed_executions = len(filtered_execution_rows) - successful_executions
    unique_execution_callers = len(execution_callers)
    repeat_execution_callers = sum(1 for count in execution_callers.values() if count > 1)
    first_time_execution_callers = unique_execution_callers - repeat_execution_callers
    first_success_modes.update(caller_first_success_mode.values())
    managed_attempts = executions_by_credential_mode.get("rhumb_managed", 0)
    managed_successes = successful_executions_by_credential_mode.get("rhumb_managed", 0)
    first_success_callers = len(caller_first_success_mode)
    managed_first_success_callers = first_success_modes.get("rhumb_managed", 0)

    latest_query_at = max((row["_created_at"] for row in query_rows), default=None)
    latest_click_at = max((row["_created_at"] for row in click_rows), default=None)
    latest_execution_at = max((row["_executed_at"] for row in filtered_execution_rows), default=None)

    execution_trend_rows = []
    for period in sorted(success_trend):
        bucket = success_trend[period]
        total = bucket["total"]
        execution_trend_rows.append(
            {
                **bucket,
                "success_rate": round(bucket["successful"] / total, 4) if total else None,
            }
        )

    funnel_stage_counts = {
        "queries": len(query_rows),
        "service_views": sum(service_views.values()),
        "provider_clicks": sum(provider_clicks.values()),
        "execute_attempts": len(filtered_execution_rows),
        "successful_executes": successful_executions,
    }
    funnel_transitions = [
        _build_funnel_transition("queries", "service_views", from_count=funnel_stage_counts["queries"], to_count=funnel_stage_counts["service_views"]),
        _build_funnel_transition("service_views", "provider_clicks", from_count=funnel_stage_counts["service_views"], to_count=funnel_stage_counts["provider_clicks"]),
        _build_funnel_transition("provider_clicks", "execute_attempts", from_count=funnel_stage_counts["provider_clicks"], to_count=funnel_stage_counts["execute_attempts"]),
        _build_funnel_transition("execute_attempts", "successful_executes", from_count=funnel_stage_counts["execute_attempts"], to_count=funnel_stage_counts["successful_executes"]),
    ]
    biggest_dropoff = max(
        funnel_transitions,
        key=lambda row: (row["dropoff_count"], row["dropoff_rate"] or 0.0),
        default=None,
    )
    readiness = _build_launch_readiness(
        unique_execution_callers=unique_execution_callers,
        successful_executions=successful_executions,
        repeat_execution_callers=repeat_execution_callers,
        first_time_execution_attempts=first_time_execution_attempts,
        first_time_execution_successes=first_time_execution_successes,
        managed_attempts=managed_attempts,
        managed_first_success_callers=managed_first_success_callers,
        first_success_callers=first_success_callers,
        biggest_dropoff=biggest_dropoff,
    )

    return {
        "window": window,
        "start_at": start_at.isoformat(),
        "generated_at": now_utc.isoformat(),
        "coverage": {
            "public_service_count": sum(1 for _ in service_rows),
        },
        "queries": {
            "total": len(query_rows),
            "machine_total": machine_queries,
            "by_source": _top_counts(by_source, limit=10),
            "top_query_types": _top_counts(by_query_type, limit=5),
            "top_services": _top_counts(top_services, limit=5),
            "top_searches": _top_counts(top_searches, limit=5),
            "unique_clients": unique_clients,
            "repeat_clients": repeat_clients,
            "repeat_client_rate": round(repeat_clients / unique_clients, 4) if unique_clients else None,
            "latest_activity_at": latest_query_at.isoformat() if latest_query_at else None,
        },
        "clicks": {
            "total": len(click_rows),
            "provider_clicks": sum(provider_clicks.values()),
            "top_provider_domains": _top_counts(provider_clicks, limit=5),
            "top_source_surfaces": _top_counts(clicks_by_surface, limit=5),
            "provider_ctr": ctr_rows[:10],
            "dispute_clicks": {
                "email": dispute_clicks_by_type.get("dispute_click", 0),
                "github": dispute_clicks_by_type.get("github_dispute_click", 0),
                "contact": dispute_clicks_by_type.get("contact_click", 0),
            },
            "latest_activity_at": latest_click_at.isoformat() if latest_click_at else None,
        },
        "funnel": {
            **funnel_stage_counts,
            "stage_transitions": funnel_transitions,
            "biggest_dropoff": biggest_dropoff,
        },
        "readiness": readiness,
        "executions": {
            "total": len(filtered_execution_rows),
            "successful": successful_executions,
            "failed": failed_executions,
            "unique_callers": unique_execution_callers,
            "first_time_callers": first_time_execution_callers,
            "repeat_callers": repeat_execution_callers,
            "repeat_caller_rate": (
                round(repeat_execution_callers / unique_execution_callers, 4)
                if unique_execution_callers
                else None
            ),
            "caller_cohorts": {
                "first_time": {
                    "attempts": first_time_execution_attempts,
                    "successful": first_time_execution_successes,
                    "failed": first_time_execution_attempts - first_time_execution_successes,
                    "success_rate": (
                        round(first_time_execution_successes / first_time_execution_attempts, 4)
                        if first_time_execution_attempts
                        else None
                    ),
                },
                "repeat": {
                    "attempts": repeat_execution_attempts,
                    "successful": repeat_execution_successes,
                    "failed": repeat_execution_attempts - repeat_execution_successes,
                    "success_rate": (
                        round(repeat_execution_successes / repeat_execution_attempts, 4)
                        if repeat_execution_attempts
                        else None
                    ),
                },
                "unattributed": {
                    "attempts": unattributed_execution_attempts,
                    "successful": unattributed_execution_successes,
                    "failed": unattributed_execution_attempts - unattributed_execution_successes,
                    "success_rate": (
                        round(unattributed_execution_successes / unattributed_execution_attempts, 4)
                        if unattributed_execution_attempts
                        else None
                    ),
                },
            },
            "credential_modes": _top_counts(executions_by_credential_mode, limit=5),
            "first_success_modes": _top_counts(first_success_modes, limit=5),
            "managed_path": {
                "attempts": managed_attempts,
                "successful": managed_successes,
                "failed": managed_attempts - managed_successes,
                "success_rate": round(managed_successes / managed_attempts, 4) if managed_attempts else None,
                "first_success_callers": managed_first_success_callers,
                "first_success_share": (
                    round(managed_first_success_callers / first_success_callers, 4)
                    if first_success_callers
                    else None
                ),
            },
            "top_interfaces": _top_counts(executions_by_interface, limit=5),
            "success_rate": (
                round(successful_executions / len(filtered_execution_rows), 4)
                if filtered_execution_rows
                else None
            ),
            "top_capabilities": _top_counts(top_capabilities, limit=5),
            "success_trend": execution_trend_rows,
            "latest_activity_at": latest_execution_at.isoformat() if latest_execution_at else None,
        },
    }
