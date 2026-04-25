"""Proxy route implementation for provisioning and agent-gated access.

Slice B additions: connection pool manager, circuit breaker, latency tracking.
Round 13 additions: schema fingerprinting, change detection, and alert pipeline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.proxy_breaker import (
    DEFAULT_TIMEOUT_THRESHOLD_MS,
    BreakerState,
    BreakerRegistry,
    CircuitBreaker,
)
from services.operational_fact_emitter import get_operational_fact_emitter
from services.proxy_latency import LatencyTracker
from services.proxy_pool import PoolManager
from services.schema_alert_pipeline import AlertDispatcher, get_alert_dispatcher
from services.schema_change_detector import (
    SchemaChange,
    SchemaChangeDetector,
    get_schema_change_detector,
)
from services.schema_fingerprint import SchemaFingerprint, fingerprint_response
from services.service_slugs import (
    canonicalize_service_slug,
    normalize_proxy_slug,
    public_service_slug,
)

from schemas.agent_identity import (
    AgentIdentitySchema,
    AgentIdentityStore,
    AgentServiceAccessSchema,
    get_agent_identity_store,
)
from services.agent_access_control import AgentAccessControl, get_agent_access_control
from services.agent_rate_limit import AgentRateLimitChecker, get_agent_rate_limit_checker
from services.proxy_auth import AuthInjectionRequest, AuthInjector, get_auth_injector
from services.proxy_credentials import get_credential_store
from services.proxy_finalizer import (
    ProxyFinalizationJob,
    ProxyFinalizer,
    get_proxy_finalizer,
)
from services.usage_metering import UsageMeterEngine, get_usage_meter_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])
admin_router = APIRouter(tags=["schema-admin"])

# Back-compat shim for existing imports in capability execution routes.
def normalize_slug(slug: str) -> str:
    """Resolve a canonical/public slug to its proxy-layer equivalent."""
    return normalize_proxy_slug(slug)


# Service registry: maps proxy-layer service names to provider domains and auth patterns.
# Public/catalog surfaces should canonicalize these names before returning them.
SERVICE_REGISTRY = {
    "stripe": {
        "domain": "api.stripe.com",
        "auth_type": "bearer_token",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "slack": {
        "domain": "slack.com",
        "auth_type": "bearer_token",
        "rate_limit": "60/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "sendgrid": {
        "domain": "api.sendgrid.com",
        "auth_type": "bearer_token",
        "rate_limit": "300/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "github": {
        "domain": "api.github.com",
        "auth_type": "bearer_token",
        "rate_limit": "5000/hour",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "twilio": {
        "domain": "api.twilio.com",
        "auth_type": "basic_auth",
        "rate_limit": "1000/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "firecrawl": {
        "domain": "api.firecrawl.dev",
        "auth_type": "bearer_token",
        "rate_limit": "500/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "apify": {
        "domain": "api.apify.com",
        "auth_type": "bearer_token",
        "rate_limit": "250/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "apollo": {
        "domain": "api.apollo.io",
        "auth_type": "api_key",
        "rate_limit": "300/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "pdl": {
        "domain": "api.peopledatalabs.com",
        "auth_type": "api_key",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    # --- Stateless utility APIs (Rhumb-managed, free-tier) ---
    "tavily": {
        "domain": "api.tavily.com",
        "auth_type": "api_key",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "exa": {
        "domain": "api.exa.ai",
        "auth_type": "api_key",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "brave-search": {
        "domain": "api.search.brave.com",
        "auth_type": "api_key",
        "rate_limit": "60/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "replicate": {
        "domain": "api.replicate.com",
        "auth_type": "bearer_token",
        "rate_limit": "600/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "algolia": {
        "domain": "80LYFTF37Y-dsn.algolia.net",
        "auth_type": "api_key",
        "rate_limit": "1000/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "e2b": {
        "domain": "api.e2b.dev",
        "auth_type": "api_key",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "unstructured": {
        "domain": "api.unstructuredapp.io",
        "auth_type": "api_key",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": 30000,  # Document processing can be slow
    },
    "google-ai": {
        "domain": "generativelanguage.googleapis.com",
        "auth_type": "api_key",
        "rate_limit": "60/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": 30000,  # AI generation can be slow
    },
    "ipinfo": {
        "domain": "api.ipinfo.io",
        "auth_type": "bearer_token",
        "rate_limit": "1000/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": DEFAULT_TIMEOUT_THRESHOLD_MS,
    },
    "scraperapi": {
        "domain": "api.scraperapi.com",
        "auth_type": "api_key",
        "rate_limit": "100/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": 30000,  # Scraping can be slow
    },
    "deepgram": {
        "domain": "api.deepgram.com",
        "auth_type": "api_key",
        "rate_limit": "200/min",
        "schema_alert_mode": "breaking_only",
        "timeout_threshold_ms": 30000,  # Audio processing can be slow
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
    upstream_latency_ms: float
    service: str
    path: str
    timestamp: float
    fail_open: bool = False


@dataclass
class ResolvedProxyContext:
    """Request-scoped control-plane state for one proxied call."""

    agent: AgentIdentitySchema
    agent_id: str
    service: str
    access: Optional[AgentServiceAccessSchema] = None
    effective_limit_qpm: Optional[int] = None


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
        _breaker_registry = BreakerRegistry(on_transition=_schedule_circuit_state_fact)
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


def _normalize_proxy_service_name(service: str) -> str:
    """Resolve public or mixed-case service ids onto proxy-layer registry keys."""
    cleaned = public_service_slug(service)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Service name required")
    return normalize_proxy_slug(cleaned)


def _public_proxy_service_name(service: str | None) -> str | None:
    """Normalize an optional proxy-layer service id onto the public slug."""
    cleaned = public_service_slug(service)
    if cleaned:
        return cleaned
    return canonicalize_service_slug(str(service).strip()) if service else None


_SCHEMA_ALERT_SEVERITIES = ("advisory", "non_breaking", "breaking")
_SCHEMA_ALERT_SEVERITY_SET = set(_SCHEMA_ALERT_SEVERITIES)


def _validated_schema_alert_severity(severity: str | None) -> str | None:
    """Normalize and validate the public admin schema-alert severity filter."""
    if severity is None:
        return None

    normalized = severity.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Severity filter cannot be blank")

    if normalized not in _SCHEMA_ALERT_SEVERITY_SET:
        valid_severities = ", ".join(_SCHEMA_ALERT_SEVERITIES)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity: use one of {valid_severities}",
        )

    return normalized


def _validated_schema_alert_service(service: str | None) -> str | None:
    """Normalize and validate the public admin schema-alert service filter."""
    if service is None:
        return None

    if not str(service).strip():
        raise HTTPException(status_code=400, detail="Service filter cannot be blank")

    return _normalize_proxy_service_name(service)


def _canonicalize_scoped_service_key(key: str) -> str:
    """Normalize ``service:agent`` proxy metric keys onto public service ids."""
    service, sep, rest = key.partition(":")
    public_service = _public_proxy_service_name(service) or service
    return f"{public_service}{sep}{rest}" if sep else public_service


def _build_request_path(path: str) -> str:
    """Normalize a proxied request path for a provider-scoped client."""
    if not path.startswith("/"):
        path = "/" + path
    return path


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


def _schedule_circuit_state_fact(
    breaker: CircuitBreaker,
    previous_state: BreakerState,
    new_state: BreakerState,
) -> None:
    event_type_by_state = {
        "open": "circuit_opened",
        "half_open": "circuit_half_opened",
        "closed": "circuit_closed",
    }
    event_type = event_type_by_state.get(new_state.value)
    if event_type is None:
        return

    get_operational_fact_emitter().schedule_circuit_state(
        service=breaker.service,
        agent_id=breaker.agent_id,
        event_type=event_type,
        new_state=new_state.value,
        failure_threshold=breaker.failure_threshold,
        timeout_threshold_ms=breaker.timeout_threshold_ms,
        cooldown_seconds=breaker.cooldown_seconds,
        metrics={
            "previous_state": previous_state.value,
            "total_calls": breaker.metrics.total_calls,
            "consecutive_failures": breaker.metrics.consecutive_failures,
            "total_failures": breaker.metrics.total_failures,
            "total_successes": breaker.metrics.total_successes,
            "times_opened": breaker.metrics.times_opened,
            "times_half_opened": breaker.metrics.times_half_opened,
            "times_closed": breaker.metrics.times_closed,
            "last_failure_time": breaker.metrics.last_failure_time,
            "last_success_time": breaker.metrics.last_success_time,
            "last_state_change": breaker.metrics.last_state_change,
        },
    )


def _max_severity(changes: tuple[SchemaChange, ...]) -> str:
    severities = {change.severity for change in changes}
    if "breaking" in severities:
        return "breaking"
    if "non_breaking" in severities:
        return "non_breaking"
    return "advisory"


def _new_proxy_timings() -> dict[str, float]:
    return {
        "auth_ms": 0.0,
        "acl_ms": 0.0,
        "rate_limit_ms": 0.0,
        "credential_inject_ms": 0.0,
        "pool_acquire_ms": 0.0,
        "upstream_ms": 0.0,
        "response_parse_ms": 0.0,
        "schema_detect_ms": 0.0,
        "finalizer_enqueue_ms": 0.0,
        "total_route_ms": 0.0,
    }


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
    request_start = time.perf_counter()
    timings = _new_proxy_timings()
    status_code = 500
    fail_open = False
    finalizer_mode = "not_run"
    finalizer_queue_depth = 0
    agent_id = "unknown"
    breaker = None
    tracker = None
    proxy_service: str | None = None
    public_request_service = _public_proxy_service_name(request.service) or str(request.service).strip()
    upstream_start: Optional[float] = None
    response_body: Any = None

    try:
        if not x_rhumb_key:
            raise HTTPException(status_code=401, detail="X-Rhumb-Key header required")

        auth_start = time.perf_counter()
        agent = await _get_identity_store().verify_api_key_with_agent(x_rhumb_key)
        timings["auth_ms"] = (time.perf_counter() - auth_start) * 1000
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid or expired governed API key")

        proxy_service = _normalize_proxy_service_name(request.service)

        resolved_context = ResolvedProxyContext(
            agent=agent,
            agent_id=agent.agent_id,
            service=proxy_service,
        )
        agent_id = resolved_context.agent_id

        acl_start = time.perf_counter()
        allowed, deny_reason, access = await _get_acl().resolve_service_access(
            resolved_context.agent,
            proxy_service,
        )
        timings["acl_ms"] = (time.perf_counter() - acl_start) * 1000
        if not allowed or access is None:
            raise HTTPException(status_code=403, detail=deny_reason or "Access denied")
        resolved_context.access = access

        rate_limit_start = time.perf_counter()
        rate_result = await _get_rate_checker().check_rate_limit_with_context(
            resolved_context.agent,
            resolved_context.access,
            proxy_service,
        )
        timings["rate_limit_ms"] = (time.perf_counter() - rate_limit_start) * 1000
        resolved_context.effective_limit_qpm = rate_result.effective_limit_qpm
        if not rate_result.allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Retry after {rate_result.retry_after_seconds}s",
                headers={"Retry-After": str(rate_result.retry_after_seconds or 60)},
            )

        service_config = _get_service_config(proxy_service)
        breaker = get_breaker_registry().get(
            proxy_service,
            agent_id,
            timeout_threshold_ms=float(
                service_config.get(
                    "timeout_threshold_ms",
                    DEFAULT_TIMEOUT_THRESHOLD_MS,
                )
            ),
        )
        if not breaker.allow_request():
            fail_open = True
            fail_response = breaker.fail_open_response()
            status_code = int(fail_response["status_code"])
            timings["total_route_ms"] = (time.perf_counter() - request_start) * 1000
            return ProxyResponse(
                status_code=status_code,
                headers=fail_response["headers"],
                body=fail_response["body"],
                latency_ms=timings["total_route_ms"],
                upstream_latency_ms=0.0,
                service=public_request_service,
                path=request.path,
                timestamp=time.time(),
                fail_open=True,
            )

        pool = get_pool_manager()
        tracker = get_latency_tracker()
        base_url = f"https://{service_config['domain']}"
        path = _build_request_path(request.path)

        headers = request.headers or {}
        request_params = request.params or {}
        request_body = request.body
        auth_method = AuthInjector.default_method_for(proxy_service)
        if auth_method is None:
            raise HTTPException(
                status_code=500,
                detail=f"No auth method configured for '{public_request_service}'",
            )

        credential_start = time.perf_counter()
        try:
            injected = _get_auth_injector().inject_request_parts(
                AuthInjectionRequest(
                    service=proxy_service,
                    agent_id=agent_id,
                    auth_method=auth_method,
                    existing_headers=headers,
                    existing_params=request_params,
                    existing_body=request_body,
                )
            )
            headers = injected.headers
            request_params = injected.params
            request_body = injected.body
        except RuntimeError as e:
            logger.warning(
                "proxy credential unavailable service=%s agent_id=%s error=%s",
                proxy_service,
                agent_id,
                e,
            )
            raise HTTPException(
                status_code=503,
                detail=f"Credential unavailable for '{public_request_service}'",
            ) from e
        finally:
            timings["credential_inject_ms"] = (
                time.perf_counter() - credential_start
            ) * 1000

        pool_start = time.perf_counter()
        client = await pool.acquire(
            proxy_service,
            agent_id,
            base_url=base_url,
        )
        timings["pool_acquire_ms"] = (time.perf_counter() - pool_start) * 1000

        try:
            upstream_start = time.perf_counter()
            try:
                proxied_response = await client.request(
                    method=request.method,
                    url=path,
                    headers=headers,
                    json=request_body,
                    params=request_params,
                )
            finally:
                timings["upstream_ms"] = (time.perf_counter() - upstream_start) * 1000
        finally:
            await pool.release(proxy_service, agent_id)

        status_code = proxied_response.status_code
        upstream_end = time.perf_counter()
        is_success = proxied_response.status_code < 500
        tracker.record(
            service=proxy_service,
            agent_id=agent_id,
            latency_ms=timings["upstream_ms"],
            perf_start=upstream_start or request_start,
            perf_end=upstream_end,
            status_code=proxied_response.status_code,
            success=is_success,
        )

        if is_success:
            breaker.record_success(latency_ms=timings["upstream_ms"])
        else:
            breaker.record_failure(status_code=proxied_response.status_code)

        parse_start = time.perf_counter()
        try:
            response_body = proxied_response.json()
        except Exception:
            response_body = proxied_response.text
        timings["response_parse_ms"] = (time.perf_counter() - parse_start) * 1000

        schema_start = time.perf_counter()
        schema_endpoint = _schema_endpoint_key(agent_id, request.path)
        fingerprint = fingerprint_response(
            response_body,
            status_code=proxied_response.status_code,
            headers=proxied_response.headers,
            latency_ms=timings["upstream_ms"],
        )
        detector = get_schema_detector()
        detection = detector.detect_changes(
            proxy_service,
            schema_endpoint,
            fingerprint,
            status_code=proxied_response.status_code,
        )

        _append_schema_events(
            service=proxy_service,
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
                service=proxy_service,
                endpoint=schema_endpoint,
                changes=detection.changes,
                alert_mode=str(service_config.get("schema_alert_mode", "breaking_only")),
            )
        timings["schema_detect_ms"] = (time.perf_counter() - schema_start) * 1000

        meter = _get_meter()
        usage_event = meter.build_metered_event(
            agent_id=agent_id,
            service=proxy_service,
            success=is_success,
            latency_ms=timings["upstream_ms"],
            response_size_bytes=len(proxied_response.content),
        )

        finalizer_start = time.perf_counter()
        finalizer_result = await _get_proxy_finalizer().enqueue_or_finalize(
            ProxyFinalizationJob(
                event=usage_event,
                service=proxy_service,
                path=request.path,
                upstream_latency_ms=timings["upstream_ms"],
                response_parse_ms=timings["response_parse_ms"],
                schema_detect_ms=timings["schema_detect_ms"],
                build_event_ms=0.0,
            )
        )
        timings["finalizer_enqueue_ms"] = (time.perf_counter() - finalizer_start) * 1000
        finalizer_mode = finalizer_result.mode
        finalizer_queue_depth = finalizer_result.queue_depth
        timings["total_route_ms"] = (time.perf_counter() - request_start) * 1000

        return ProxyResponse(
            status_code=proxied_response.status_code,
            headers=dict(proxied_response.headers),
            body=response_body,
            latency_ms=timings["total_route_ms"],
            upstream_latency_ms=timings["upstream_ms"],
            service=public_request_service,
            path=request.path,
            timestamp=time.time(),
            fail_open=False,
        )

    except HTTPException as exc:
        status_code = exc.status_code
        raise
    except Exception as e:
        status_code = 500
        error_end = time.perf_counter()
        timings["total_route_ms"] = (error_end - request_start) * 1000
        error_latency_ms = timings["total_route_ms"]

        logger.warning(
            "proxy unhandled error service=%s public_service=%s agent_id=%s error=%s",
            proxy_service,
            public_request_service,
            agent_id,
            e,
        )

        if breaker is not None:
            breaker.record_failure()
        if tracker is not None and agent_id != "unknown":
            tracker.record(
                service=proxy_service or public_request_service,
                agent_id=agent_id,
                latency_ms=error_latency_ms,
                perf_start=upstream_start or request_start,
                perf_end=error_end,
                status_code=500,
                success=False,
            )

        if agent_id != "unknown":
            await _get_meter().record_metered_call(
                agent_id=agent_id,
                service=proxy_service or public_request_service,
                success=False,
                latency_ms=error_latency_ms,
                response_size_bytes=0,
            )
            finalizer_mode = "error_inline_metered"

        raise HTTPException(
            status_code=500,
            detail=f"Proxy error for '{public_request_service}'",
        ) from e
    finally:
        timings["total_route_ms"] = (time.perf_counter() - request_start) * 1000
        logger.info(
            "proxy full-path timings service=%s method=%s path=%s agent_id=%s status_code=%d fail_open=%s auth_ms=%.1f acl_ms=%.1f rate_limit_ms=%.1f credential_inject_ms=%.1f pool_acquire_ms=%.1f upstream_ms=%.1f response_parse_ms=%.1f schema_detect_ms=%.1f finalizer_enqueue_ms=%.1f finalizer_mode=%s queue_depth=%d total_route_ms=%.1f",
            request.service,
            request.method,
            request.path,
            agent_id,
            status_code,
            fail_open,
            timings["auth_ms"],
            timings["acl_ms"],
            timings["rate_limit_ms"],
            timings["credential_inject_ms"],
            timings["pool_acquire_ms"],
            timings["upstream_ms"],
            timings["response_parse_ms"],
            timings["schema_detect_ms"],
            timings["finalizer_enqueue_ms"],
            finalizer_mode,
            finalizer_queue_depth,
            timings["total_route_ms"],
        )


@router.get("/services")
async def list_services() -> dict:
    """List all available services in the proxy registry.

    Each entry includes a ``callable`` flag indicating whether a live
    credential is loaded.  Services where ``callable`` is ``false`` will
    return 503 if a proxy call is attempted.
    """
    credential_store = get_credential_store()
    callable_set = set(credential_store.callable_services())

    services = []
    for service_name, config in SERVICE_REGISTRY.items():
        canonical_slug = canonicalize_service_slug(service_name)
        services.append(
            {
                "name": canonical_slug,
                "proxy_name": service_name,
                "canonical_slug": canonical_slug,
                "domain": config["domain"],
                "auth_type": config["auth_type"],
                "rate_limit": config["rate_limit"],
                "callable": service_name in callable_set,
            }
        )
    return {
        "data": {
            "services": services,
            "total": len(services),
            "callable_count": len(callable_set),
        },
        "error": None,
    }


@router.get("/stats")
async def proxy_stats() -> dict:
    """Get proxy statistics: latency, circuit breaker states, pool utilization."""
    tracker = get_latency_tracker()
    breaker_reg = get_breaker_registry()
    pool = get_pool_manager()
    emitter = get_operational_fact_emitter()
    credential_store = get_credential_store()

    global_snapshot = tracker.get_global_snapshot()
    per_service = tracker.get_all_snapshots()

    callable_svcs = credential_store.callable_services()
    callable_public_svcs = {
        _public_proxy_service_name(service) or service for service in callable_svcs
    }

    circuits: dict[str, str] = {}
    for key, state in breaker_reg.get_all_states().items():
        circuits[_canonicalize_scoped_service_key(key)] = state

    per_service_payload: dict[str, dict[str, Any]] = {}
    for key, snap in per_service.items():
        snapshot_payload = snap.to_dict()
        snapshot_payload["service"] = _public_proxy_service_name(snapshot_payload.get("service"))
        per_service_payload[_canonicalize_scoped_service_key(key)] = snapshot_payload

    pool_payload: dict[str, dict[str, Any]] = {}
    for key, metrics in pool.get_all_metrics().items():
        pool_payload[_canonicalize_scoped_service_key(key)] = {
            "pool_size": metrics.pool_size,
            "active": metrics.active_connections,
            "utilization": round(metrics.utilization, 3),
            "reuse_ratio": round(metrics.reuse_ratio, 3),
            "total_acquired": metrics.total_acquired,
        }

    return {
        "data": {
            # services_registered: total entries in SERVICE_REGISTRY (may lack credentials)
            # services_callable: subset that have a live credential — actually reachable
            "services_registered": len(SERVICE_REGISTRY),
            "services_callable": len(callable_public_svcs),
            "circuits": circuits,
            "latency": {
                "p50_ms": round(global_snapshot.p50_ms, 3),
                "p95_ms": round(global_snapshot.p95_ms, 3),
                "p99_ms": round(global_snapshot.p99_ms, 3),
                "mean_ms": round(global_snapshot.mean_ms, 3),
                "total_calls": global_snapshot.count,
            },
            "per_service": per_service_payload,
            "pools": pool_payload,
            "operational_facts": emitter.get_stats(),
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
    proxy_service = _normalize_proxy_service_name(service)
    _get_service_config(proxy_service)  # Validate service exists

    tracker = get_latency_tracker()
    snapshot = tracker.get_snapshot(proxy_service, agent_id)
    breaker_reg = get_breaker_registry()
    breaker = breaker_reg.get(proxy_service, agent_id)
    pool = get_pool_manager()
    pool_metrics = pool.get_metrics(proxy_service, agent_id)

    latency_payload = snapshot.to_dict()
    latency_payload["service"] = _public_proxy_service_name(latency_payload.get("service"))

    return {
        "data": {
            "latency": latency_payload,
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
    proxy_service = _normalize_proxy_service_name(service)
    _get_service_config(proxy_service)

    detector = get_schema_detector()
    schema_endpoint = _schema_endpoint_key(agent_id, endpoint)
    fingerprint = detector.get_latest_fingerprint(
        proxy_service,
        schema_endpoint,
        status_code=200,
    )
    history = detector.get_change_history(
        proxy_service,
        schema_endpoint,
        limit=limit,
        status_code=200,
    )

    recent_events = [
        event
        for event in reversed(_schema_events)
        if event.get("service") == proxy_service and event.get("endpoint") == schema_endpoint
    ][:limit]

    return {
        "data": {
            "service": _public_proxy_service_name(proxy_service),
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
            "events": [
                {
                    **event,
                    "service": _public_proxy_service_name(event.get("service")),
                }
                for event in recent_events
            ],
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
    proxy_service = _validated_schema_alert_service(service)
    normalized_severity = _validated_schema_alert_severity(severity)
    dispatcher = get_schema_alert_dispatcher()
    alerts = dispatcher.query_alerts(
        service=proxy_service,
        severity=normalized_severity,
        limit=limit,
    )

    return {
        "data": {
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "service": _public_proxy_service_name(alert.service),
                    "endpoint": alert.endpoint,
                    "severity": alert.severity,
                    "change_detail": {
                        **alert.change_detail,
                        "service": _public_proxy_service_name(
                            alert.change_detail.get("service")
                        ),
                    }
                    if isinstance(alert.change_detail, dict)
                    else alert.change_detail,
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
