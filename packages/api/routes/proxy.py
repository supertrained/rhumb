"""Proxy route implementation for provisioning and agent-gated access."""

import json
import time
from typing import Any, Optional
from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, Field
import httpx

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
    headers: Optional[dict] = Field(None, description="Custom headers (auth headers added by proxy)")


class ProxyResponse(BaseModel):
    """Schema for proxy response."""

    status_code: int
    headers: dict[str, str]
    body: Any
    latency_ms: float
    service: str
    path: str
    timestamp: float


# Connection pool (will be replaced with Redis in Slice B)
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client for pooled connections."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20)
        )
    return _http_client


def _get_service_config(service: str) -> dict:
    """Get service configuration from registry."""
    if service not in SERVICE_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Service '{service}' not found. Available: {', '.join(SERVICE_REGISTRY.keys())}"
        )
    return SERVICE_REGISTRY[service]


def _build_url(service: str, path: str) -> str:
    """Build full URL for proxied request."""
    config = _get_service_config(service)
    domain = config["domain"]
    # Ensure path starts with /
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{domain}{path}"


@router.post("/", response_model=ProxyResponse)
async def proxy_request(
    request: ProxyRequest,
    authorization: Optional[str] = Header(None),
) -> ProxyResponse:
    """
    Proxy a request to a provider API.

    The proxy:
    - Validates the service exists
    - Builds the full URL
    - Forwards the request with auth headers
    - Measures latency
    - Returns the response

    Parameters:
    - request: ProxyRequest with service, method, path, body, params, headers
    - authorization: Bearer token or credentials (via Authorization header)

    Returns ProxyResponse with status, headers, body, latency, and metadata.
    """
    start_time = time.time()

    try:
        # Validate service
        config = _get_service_config(request.service)

        # Build URL
        url = _build_url(request.service, request.path)

        # Prepare headers
        headers = request.headers or {}

        # Inject authorization header if provided
        if authorization:
            headers["Authorization"] = authorization

        # Get async client
        client = await get_http_client()

        # Forward request
        proxied_response = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            json=request.body,
            params=request.params,
        )

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Log latency
        print(
            f"[PROXY] {request.service} {request.method} {request.path} "
            f"→ {proxied_response.status_code} ({latency_ms:.1f}ms)"
        )

        # Parse response body
        try:
            response_body = proxied_response.json()
        except Exception:
            response_body = proxied_response.text

        # Build response
        return ProxyResponse(
            status_code=proxied_response.status_code,
            headers=dict(proxied_response.headers),
            body=response_body,
            latency_ms=latency_ms,
            service=request.service,
            path=request.path,
            timestamp=time.time(),
        )

    except HTTPException:
        raise
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        raise HTTPException(
            status_code=500,
            detail=f"Proxy error: {str(e)}",
        )


@router.get("/services")
async def list_services() -> dict:
    """List all available services in the proxy registry."""
    services = []
    for service_name, config in SERVICE_REGISTRY.items():
        services.append({
            "name": service_name,
            "domain": config["domain"],
            "auth_type": config["auth_type"],
            "rate_limit": config["rate_limit"],
        })
    return {
        "data": {
            "services": services,
            "total": len(services),
        },
        "error": None,
    }


@router.get("/stats")
async def proxy_stats() -> dict:
    """
    Get proxy statistics (placeholder for Slice B connection pool stats).

    Will include latency distribution, circuit breaker status, etc.
    """
    return {
        "data": {
            "services_online": len(SERVICE_REGISTRY),
            "circuits": {},
            "latency": {
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
            },
        },
        "error": None,
    }
