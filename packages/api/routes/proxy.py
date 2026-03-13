"""Proxy route implementation for provisioning and agent-gated access.

Slice B additions: connection pool manager, circuit breaker, latency tracking.
Round 13 additions: schema fingerprinting, change detection, and alert pipeline.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.proxy_breaker import BreakerRegistry
from services.proxy_latency import LatencyTracker
from services.proxy_pool import PoolManager
from services.schema_alert_pipeline import AlertDispatcher, get_alert_dispatcher
from services.schema_change_detector import (
    SchemaChange,
    SchemaChangeDetector,
    get_schema_change_detector,
)
from services.schema_fingerprint import SchemaFingerprint, fingerprint_response

from schemas.agent_identity import AgentIdentityStore, get_agent_identity_store
from services.agent_access_control import AgentAccessControl, get_agent_access_control
from services.agent_rate_limit import AgentRateLimitChecker, get_agent_rate_limit_checker
from services.proxy_auth import AuthInjectionRequest, AuthMethod, AuthInjector, get_auth_injector
from services.proxy_finalizer import (
    ProxyFinalizationJob,
    ProxyFinalizer,
    get_proxy_finalizer,
)
from services.usage_metering import UsageMeterEngine, get_usage_meter_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])
admin_router = APIRouter(tags=["schema-admin"])

# Service registry: maps service names to provider domains and auth patterns
SERVICE_REGISTRY = {
    "stripe": {
        "domain": "api.stripe.com",
        "auth_type": "bearer_token",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
    },
    "slack": {
        "domain": "slack.com",
        "auth_type": "bearer_token",
        "rate_limit": "60/min",
        "schema_alert_mode": "breaking_only",
    },
    "sendgrid": {
        "domain": "api.sendgrid.com",
        "auth_type": "bearer_token",
        "rate_limit": "300/min",
        "schema_alert_mode": "breaking_only",
    },
    "github": {
        "domain": "api.github.com",
        "auth_type": "bearer_token",
        "rate_limit": "5000/hour",
        "schema_alert_mode": "breaking_only",
    },
    "twilio": {
        "domain": "api.twilio.com",
        "auth_type": "basic_auth",
        "rate_limit": "1000/min",
        "schema_alert_mode": "breaking_only",
    },
}


class ProxyRequest(BaseModel):
    """Schema for proxy request."""

    service: str = Field(..., description="Service name (e.g., 'stripe')")
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="API path (e.g., '/v1/customers')")
    body: Optional[dict] = Field(None, description="Request body for POST/PUT/PATCH")
    params: Optional[dict] = Field(None, description="Query parameters")
    headers: Optional[dict] = Field(
        None, description="Custom headers (auth headers added by proxy)"
    )
    agent_id: Optional[str] = Field("default", description="Agent identity for pooling")


class ProxyResponse(BaseModel):
    """Schema for proxy response."""

    status_code: int
    headers: dict[str, str]
    body: Any
    latency_ms: float
    service: str
    path: str
    timestamp: float
    fail_open: bool = False


# Singleton instances (module-level, replaced in tests)
_pool_manager: Optional[PoolManager] = None
_breaker_registry: Optional[BreakerRegistry] = None
_latency_tracker: Optional[LatencyTracker] = None
_schema_detector: Optional[SchemaChangeDetector] = None
_schema_alert_dispatcher: Optional[AlertDispatcher] = None

# Lightweight in-memory schema events storage.
_schema_events: list[dict[str, Any]] = []

# Control-plane singletons (GAP-1)
_identity_store: Optional[AgentIdentityStore] = None
_acl_instance: Optional[AgentAccessControl] = None
_rate_checker_instance: Optional[AgentRateLimitChecker] = None
_auth_injector_instance: Optional[AuthInjector] = None
_meter_instance: Optional[UsageMeterEngine] = None
_proxy_finalizer: Optional[ProxyFinalizer] = None

# Legacy fallback client (used only if pool manager is not initialized)
_http_client: Optional[httpx.AsyncClient] = None


def get_pool_manager() -> PoolManager:
    """Get or create the global pool manager."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = PoolManager()
    return _pool_manager


def get_breaker_registry() -> BreakerRegistry:
    """Get or create the global breaker registry."""
    global _breaker_registry
    if _breaker_registry is None:
        _breaker_registry = BreakerRegistry()
    return _breaker_registry


def get_latency_tracker() -> LatencyTracker:
    """Get or create the global latency tracker."""
    global _latency_tracker
    if _latency_tracker is None:
        _latency_tracker = LatencyTracker()
    return _latency_tracker


def get_schema_detector() -> SchemaChangeDetector:
    """Get or create the global schema change detector."""
    global _schema_detector
    if _schema_detector is None:
        _schema_detector = get_schema_change_detector()
    return _schema_detector


def get_schema_alert_dispatcher() -> AlertDispatcher:
    """Get or create the global schema alert dispatcher."""
    global _schema_alert_dispatcher
    if _schema_alert_dispatcher is None:
        _schema_alert_dispatcher = get_alert_dispatcher()
    return _schema_alert_dispatcher


def _get_identity_store() -> AgentIdentityStore:
    global _identity_store
    if _identity_store is None:
        _identity_store = get_agent_identity_store()
    return _identity_store


def _get_acl() -> AgentAccessControl:
    global _acl_instance
    if _acl_instance is None:
        _acl_instance = get_agent_access_control()
    return _acl_instance


def _get_rate_checker() -> AgentRateLimitChecker:
    global _rate_checker_instance
    if _rate_checker_instance is None:
        _rate_checker_instance = get_agent_rate_limit_checker()
    return _rate_checker_instance


def _get_auth_injector() -> AuthInjector:
    global _auth_injector_instance
    if _auth_injector_instance is None:
        _auth_injector_instance = get_auth_injector()
    return _auth_injector_instance


def _get_meter() -> UsageMeterEngine:
    global _meter_instance
    if _meter_instance is None:
        _meter_instance = get_usage_meter_engine()
    return _meter_instance


def _get_proxy_finalizer() -> ProxyFinalizer:
    global _proxy_finalizer
    if _proxy_finalizer is None:
        _proxy_finalizer = get_proxy_finalizer(meter_engine=_get_meter())
    return _proxy_finalizer


async def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client (legacy fallback, prefer pool manager)."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
        )
    return _http_client


def _get_service_config(service: str) -> dict:
    """Get service configuration from registry."""
    if service not in SERVICE_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Service '{service}' not found. "
                f"Available: {', '.join(SERVICE_REGISTRY.keys())}"
            ),
        )
    return SERVICE_REGISTRY[service]


def _build_url(service: str, path: str) -> str:
    """Build full URL for proxied request."""
    config = _get_service_config(service)
    domain = config["domain"]
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{domain}{path}"


def _schema_endpoint_key(agent_id: str, endpoint_path: str) -> str:
    clean_path = endpoint_path.lstrip("/")
    return f"{agent_id}:{clean_path}"


def _append_schema_events(
    *,
    service: str,
    endpoint: str,
    fingerprint: SchemaFingerprint,
    status_code: int,
    changes: tuple[SchemaChange, ...],
    warnings: tuple[str, ...],
) -> None:
    timestamp = datetime.now(tz=UTC).isoformat()

    if not changes:
        _schema_events.append(
            {
                "service": service,
                "endpoint": endpoint,
                "fingerprint_hash": fingerprint.fingerprint_hash,
                "change_type": "none",
                "severity": "advisory",
                "captured_at": timestamp,
                "status_code": status_code,
                "warnings": list(warnings),
            }
        )
        return

    for change in changes:
        _schema_events.append(
            {
                "service": service,
                "endpoint": endpoint,
                "fingerprint_hash": fingerprint.fingerprint_hash,
                "change_type": change.change_type,
                "severity": change.severity,
                "path": change.path,
                "old_type": change.old_type,
                "new_type": change.new_type,
                "detail": change.detail,
                "similarity": change.similarity,
                "captured_at": timestamp,
                "status_code": status_code,
                "warnings": list(warnings),
            }
        )


async def _dispatch_schema_alert_task(
    *,
    service: str,
    endpoint: str,
    changes: tuple[SchemaChange, ...],
    alert_mode: str,
) -> None:
    dispatcher = get_schema_alert_dispatcher()
    await dispatcher.dispatch(
        service=service,
        endpoint=endpoint,
        changes=changes,
        alert_mode=alert_mode,
    )


def _max_severity(changes: tuple[SchemaChange, ...]) -> str:
    severities = {change.severity for change in changes}
    if "breaking" in severities:
        return "breaking"
    if "non_breaking" in severities:
        return "non_breaking"
    return "advisory"


@router.post("/", response_model=ProxyResponse)
async def proxy_request(
    request: ProxyRequest,
    background_tasks: BackgroundTasks,
    x_rhumb_key: Optional[str] = Header(None, alias="X-Rhumb-Key"),
) -> ProxyResponse:
    """Proxy a request to a provider API.

    Integrates connection pooling, circuit breaker, latency tracking.

    The proxy:
    - Checks circuit breaker state (fail-open if OPEN)
    - Acquires a pooled connection
    - Forwards the request with auth headers
    - Measures latency with perf_counter precision
    - Records metrics
    - Performs schema drift detection (non-blocking alerts)
    - Returns response with circuit breaker signal
    """
    # --- Control plane: Authenticate agent via X-Rhumb-Key header ---
    if not x_rhumb_key:
        raise HTTPException(status_code=401, detail="X-Rhumb-Key header required")
    agent_id = await _get_identity_store().verify_api_key(x_rhumb_key)
    if agent_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired Rhumb API key")

    # --- Control plane: ACL check ---
    allowed, deny_reason = await _get_acl().can_access_service(
        agent_id=agent_id,
        service=request.service,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=deny_reason or "Access denied")

    # --- Control plane: Rate limit check ---
    rate_result = await _get_rate_checker().check_rate_limit(
        agent_id=agent_id,
        service=request.service,
    )
    if not rate_result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {rate_result.retry_after_seconds}s",
            headers={"Retry-After": str(rate_result.retry_after_seconds or 60)},
        )

    perf_start = time.perf_counter()

    # Circuit breaker check
    breaker_reg = get_breaker_registry()
    breaker = breaker_reg.get(request.service, agent_id)

    if not breaker.allow_request():
        fail_response = breaker.fail_open_response()
        return ProxyResponse(
            status_code=fail_response["status_code"],
            headers=fail_response["headers"],
            body=fail_response["body"],
            latency_ms=0.0,
            service=request.service,
            path=request.path,
            timestamp=time.time(),
            fail_open=True,
        )

    pool = get_pool_manager()
    tracker = get_latency_tracker()

    try:
        # Validate service
        service_config = _get_service_config(request.service)

        # Build URL
        url = _build_url(request.service, request.path)

        # --- Control plane: Inject provider credential from vault ---
        headers = request.headers or {}
        auth_method = AuthInjector.default_method_for(request.service)
        if auth_method is None:
            raise HTTPException(status_code=500, detail=f"No auth method configured for '{request.service}'")
        try:
            headers = _get_auth_injector().inject(
                AuthInjectionRequest(
                    service=request.service,
                    agent_id=agent_id,
                    auth_method=auth_method,
                    existing_headers=headers,
                )
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=f"Credential unavailable: {e}")

        # Acquire pooled client
        client = await pool.acquire(request.service, agent_id)

        try:
            # Forward request
            proxied_response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                json=request.body,
                params=request.params,
            )
        finally:
            # Always release back to pool
            await pool.release(request.service, agent_id)

        perf_end = time.perf_counter()
        latency_ms = (perf_end - perf_start) * 1000

        # Record latency
        is_success = proxied_response.status_code < 500
        tracker.record(
            service=request.service,
            agent_id=agent_id,
            latency_ms=latency_ms,
            perf_start=perf_start,
            perf_end=perf_end,
            status_code=proxied_response.status_code,
            success=is_success,
        )

        # Update circuit breaker
        if is_success:
            breaker.record_success(latency_ms=latency_ms)
        else:
            breaker.record_failure(status_code=proxied_response.status_code)

        # Log latency
        print(
            f"[PROXY] {request.service} {request.method} {request.path} "
            f"-> {proxied_response.status_code} ({latency_ms:.1f}ms)"
        )

        upstream_done_perf = time.perf_counter()

        # Parse response body
        parse_start = time.perf_counter()
        try:
            response_body: Any = proxied_response.json()
        except Exception:
            response_body = proxied_response.text
        response_parse_ms = (time.perf_counter() - parse_start) * 1000

        # Schema detection (non-blocking alert dispatch)
        schema_start = time.perf_counter()
        schema_endpoint = _schema_endpoint_key(agent_id, request.path)
        fingerprint = fingerprint_response(
            response_body,
            status_code=proxied_response.status_code,
            headers=proxied_response.headers,
            latency_ms=latency_ms,
        )
        detector = get_schema_detector()
        detection = detector.detect_changes(
            request.service,
            schema_endpoint,
            fingerprint,
            status_code=proxied_response.status_code,
        )

        _append_schema_events(
            service=request.service,
            endpoint=schema_endpoint,
            fingerprint=fingerprint,
            status_code=proxied_response.status_code,
            changes=detection.changes,
            warnings=detection.warnings,
        )

        if detection.changes and detector.alert_required(
            detection.changes,
            include_non_breaking=(service_config.get("schema_alert_mode") == "all"),
        ):
            background_tasks.add_task(
                _dispatch_schema_alert_task,
                service=request.service,
                endpoint=schema_endpoint,
                changes=detection.changes,
                alert_mode=str(service_config.get("schema_alert_mode", "breaking_only")),
            )
        schema_detect_ms = (time.perf_counter() - schema_start) * 1000

        # --- Control plane: finalize metered usage off the success hot path ---
        meter = _get_meter()
        build_start = time.perf_counter()
        usage_event = meter.build_metered_event(
            agent_id=agent_id,
            service=request.service,
            success=is_success,
            latency_ms=latency_ms,
            response_size_bytes=len(proxied_response.content),
        )
        build_event_ms = (time.perf_counter() - build_start) * 1000

        finalizer_result = await _get_proxy_finalizer().enqueue_or_finalize(
            ProxyFinalizationJob(
                event=usage_event,
                service=request.service,
                path=request.path,
                upstream_latency_ms=latency_ms,
                response_parse_ms=response_parse_ms,
                schema_detect_ms=schema_detect_ms,
                build_event_ms=build_event_ms,
            )
        )
        post_upstream_sync_ms = (time.perf_counter() - upstream_done_perf) * 1000

        logger.info(
            "proxy phase timings service=%s method=%s path=%s upstream_ms=%.1f response_parse_ms=%.1f schema_detect_ms=%.1f build_event_ms=%.1f post_upstream_sync_ms=%.1f finalizer_mode=%s queue_depth=%d",
            request.service,
            request.method,
            request.path,
            latency_ms,
            response_parse_ms,
            schema_detect_ms,
            build_event_ms,
            post_upstream_sync_ms,
            finalizer_result.mode,
            finalizer_result.queue_depth,
        )

        return ProxyResponse(
            status_code=proxied_response.status_code,
            headers=dict(proxied_response.headers),
            body=response_body,
            latency_ms=latency_ms,
            service=request.service,
            path=request.path,
            timestamp=time.time(),
            fail_open=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        perf_end = time.perf_counter()
        latency_ms = (perf_end - perf_start) * 1000

        # Record failure in breaker and tracker
        breaker.record_failure()
        tracker.record(
            service=request.service,
            agent_id=agent_id,
            latency_ms=latency_ms,
            perf_start=perf_start,
            perf_end=perf_end,
            status_code=500,
            success=False,
        )

        await _get_meter().record_metered_call(
            agent_id=agent_id,
            service=request.service,
            success=False,
            latency_ms=latency_ms,
            response_size_bytes=0,
        )

        raise HTTPException(
            status_code=500,
            detail=f"Proxy error: {str(e)}",
        )


@router.get("/services")
async def list_services() -> dict:
    """List all available services in the proxy registry."""
    services = []
    for service_name, config in SERVICE_REGISTRY.items():
        services.append(
            {
                "name": service_name,
                "domain": config["domain"],
                "auth_type": config["auth_type"],
                "rate_limit": config["rate_limit"],
            }
        )
    return {
        "data": {
            "services": services,
            "total": len(services),
        },
        "error": None,
    }


@router.get("/stats")
async def proxy_stats() -> dict:
    """Get proxy statistics: latency, circuit breaker states, pool utilization."""
    tracker = get_latency_tracker()
    breaker_reg = get_breaker_registry()
    pool = get_pool_manager()

    global_snapshot = tracker.get_global_snapshot()
    per_service = tracker.get_all_snapshots()

    return {
        "data": {
            "services_online": len(SERVICE_REGISTRY),
            "circuits": breaker_reg.get_all_states(),
            "latency": {
                "p50_ms": round(global_snapshot.p50_ms, 3),
                "p95_ms": round(global_snapshot.p95_ms, 3),
                "p99_ms": round(global_snapshot.p99_ms, 3),
                "mean_ms": round(global_snapshot.mean_ms, 3),
                "total_calls": global_snapshot.count,
            },
            "per_service": {
                key: snap.to_dict() for key, snap in per_service.items()
            },
            "pools": {
                key: {
                    "pool_size": m.pool_size,
                    "active": m.active_connections,
                    "utilization": round(m.utilization, 3),
                    "reuse_ratio": round(m.reuse_ratio, 3),
                    "total_acquired": m.total_acquired,
                }
                for key, m in pool.get_all_metrics().items()
            },
        },
        "error": None,
    }


@router.get("/metrics/{service}")
async def proxy_metrics(service: str, agent_id: str = "default") -> dict:
    """Get latency metrics for a specific service.

    Args:
        service: Provider service name.
        agent_id: Agent identifier (query param, defaults to 'default').

    Returns:
        Latency snapshot with P50/P95/P99 percentiles.
    """
    _get_service_config(service)  # Validate service exists

    tracker = get_latency_tracker()
    snapshot = tracker.get_snapshot(service, agent_id)
    breaker_reg = get_breaker_registry()
    breaker = breaker_reg.get(service, agent_id)
    pool = get_pool_manager()
    pool_metrics = pool.get_metrics(service, agent_id)

    return {
        "data": {
            "latency": snapshot.to_dict(),
            "circuit_state": breaker.state.value,
            "pool": {
                "pool_size": pool_metrics.pool_size if pool_metrics else 0,
                "active": pool_metrics.active_connections if pool_metrics else 0,
                "utilization": round(pool_metrics.utilization, 3) if pool_metrics else 0.0,
                "reuse_ratio": round(pool_metrics.reuse_ratio, 3) if pool_metrics else 0.0,
            },
        },
        "error": None,
    }


@admin_router.get("/admin/schema/{service}/{endpoint:path}")
async def get_schema_snapshot(
    service: str,
    endpoint: str,
    agent_id: str = Query(default="default"),
    limit: int = Query(default=5, ge=1, le=50),
) -> dict[str, Any]:
    """Return latest schema fingerprint and recent change history."""
    _get_service_config(service)

    detector = get_schema_detector()
    schema_endpoint = _schema_endpoint_key(agent_id, endpoint)
    fingerprint = detector.get_latest_fingerprint(service, schema_endpoint, status_code=200)
    history = detector.get_change_history(
        service,
        schema_endpoint,
        limit=limit,
        status_code=200,
    )

    recent_events = [
        event
        for event in reversed(_schema_events)
        if event.get("service") == service and event.get("endpoint") == schema_endpoint
    ][:limit]

    return {
        "data": {
            "service": service,
            "endpoint": endpoint,
            "agent_id": agent_id,
            "latest_fingerprint": {
                "hash": fingerprint.fingerprint_hash if fingerprint else None,
                "schema_tree": fingerprint.schema_tree if fingerprint else None,
                "max_depth": fingerprint.max_depth if fingerprint else 0,
            },
            "changes": [
                {
                    "change_type": change.change_type,
                    "path": change.path,
                    "severity": change.severity,
                    "old_type": change.old_type,
                    "new_type": change.new_type,
                    "detail": change.detail,
                    "similarity": change.similarity,
                }
                for change in history
            ],
            "events": recent_events,
        },
        "error": None,
    }


@admin_router.get("/admin/schema-alerts")
async def list_schema_alerts(
    service: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    """Query recent schema alerts (in-app channel)."""
    dispatcher = get_schema_alert_dispatcher()
    alerts = dispatcher.query_alerts(service=service, severity=severity, limit=limit)

    return {
        "data": {
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "service": alert.service,
                    "endpoint": alert.endpoint,
                    "severity": alert.severity,
                    "change_detail": alert.change_detail,
                    "alert_sent_at": (
                        alert.alert_sent_at.isoformat() if alert.alert_sent_at else None
                    ),
                    "webhook_url": alert.webhook_url,
                    "webhook_status": alert.webhook_status,
                    "retry_count": alert.retry_count,
                    "retry_at": alert.retry_at.isoformat() if alert.retry_at else None,
                    "created_at": alert.created_at.isoformat(),
                }
                for alert in alerts
            ],
            "count": len(alerts),
        },
        "error": None,
    }
