"""Proxy route implementation for provisioning and agent-gated access.

Slice B additions: connection pool manager, circuit breaker, latency tracking.
"""

import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services.proxy_breaker import BreakerRegistry, BreakerState
from services.proxy_latency import LatencyTracker
from services.proxy_pool import PoolManager

router = APIRouter(tags=["proxy"])

# Service registry: maps service names to provider domains and auth patterns
SERVICE_REGISTRY = {
    "stripe": {
        "domain": "api.stripe.com",
        "auth_type": "bearer_token",
        "rate_limit": "100/min",
    },
    "slack": {
        "domain": "slack.com",
        "auth_type": "bearer_token",
        "rate_limit": "60/min",
    },
    "sendgrid": {
        "domain": "api.sendgrid.com",
        "auth_type": "bearer_token",
        "rate_limit": "300/min",
    },
    "github": {
        "domain": "api.github.com",
        "auth_type": "bearer_token",
        "rate_limit": "5000/hour",
    },
    "twilio": {
        "domain": "api.twilio.com",
        "auth_type": "basic_auth",
        "rate_limit": "1000/min",
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
            detail=f"Service '{service}' not found. Available: {', '.join(SERVICE_REGISTRY.keys())}",
        )
    return SERVICE_REGISTRY[service]


def _build_url(service: str, path: str) -> str:
    """Build full URL for proxied request."""
    config = _get_service_config(service)
    domain = config["domain"]
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{domain}{path}"


@router.post("/", response_model=ProxyResponse)
async def proxy_request(
    request: ProxyRequest,
    authorization: Optional[str] = Header(None),
) -> ProxyResponse:
    """Proxy a request to a provider API.

    Integrates connection pooling, circuit breaker, and latency tracking.

    The proxy:
    - Checks circuit breaker state (fail-open if OPEN)
    - Acquires a pooled connection
    - Forwards the request with auth headers
    - Measures latency with perf_counter precision
    - Records metrics
    - Returns response with circuit breaker signal
    """
    agent_id = request.agent_id or "default"
    perf_start = time.perf_counter()
    start_time = time.time()

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
        _get_service_config(request.service)

        # Build URL
        url = _build_url(request.service, request.path)

        # Prepare headers
        headers = request.headers or {}
        if authorization:
            headers["Authorization"] = authorization

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

        # Parse response body
        try:
            response_body = proxied_response.json()
        except Exception:
            response_body = proxied_response.text

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
