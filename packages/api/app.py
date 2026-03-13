"""FastAPI application factory and router registration."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from middleware.query_logging import QueryLoggingMiddleware
from routes import (
    admin_agents,
    admin_billing,
    leaderboard,
    probes,
    proxy,
    scores,
    search,
    services,
    tester_fleet,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Application lifespan: initialize async dependencies at startup."""
    # Initialize Supabase-backed stores up front so the HTTP control plane,
    # ACL/rate-limit path, and durable metering all point at the same identity source.
    from db.client import get_supabase_client
    from schemas.agent_identity import get_agent_identity_store
    from services.proxy_auth import get_auth_injector
    from services.proxy_finalizer import get_proxy_finalizer
    from services.usage_metering import get_usage_meter_engine

    supabase = await get_supabase_client()
    get_agent_identity_store(supabase)
    logger.info("Agent identity: Supabase client initialized")

    get_auth_injector()
    logger.info("Auth injector: credential store warmed")

    meter = get_usage_meter_engine()
    if await meter.ensure_supabase():
        logger.info("Durable metering: Supabase client initialized")
    else:
        logger.warning("Durable metering: Supabase unavailable — using in-memory fallback")

    proxy_finalizer = get_proxy_finalizer(meter)
    await proxy_finalizer.start()
    logger.info("Proxy finalizer worker started")

    try:
        yield
    finally:
        await proxy_finalizer.stop(drain=True)
        logger.info("Proxy finalizer worker drained")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Rhumb API", version="0.0.1", lifespan=_lifespan)

    # ── Middleware ──
    application.add_middleware(QueryLoggingMiddleware)

    # ── Routers ──
    application.include_router(services.router, prefix="/v1", tags=["services"])
    application.include_router(probes.router, prefix="/v1", tags=["probes"])
    application.include_router(scores.router, prefix="/v1", tags=["scores"])
    application.include_router(search.router, prefix="/v1", tags=["search"])
    application.include_router(leaderboard.router, prefix="/v1", tags=["leaderboard"])
    application.include_router(tester_fleet.router, prefix="/v1", tags=["tester-fleet"])
    application.include_router(proxy.router, prefix="/v1/proxy", tags=["proxy"])
    application.include_router(proxy.admin_router, prefix="/v1", tags=["schema-admin"])
    application.include_router(
        admin_agents.router, prefix="/v1/admin", tags=["admin-agents"]
    )
    application.include_router(
        admin_billing.router, prefix="/v1", tags=["admin-billing"]
    )

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Simple liveness endpoint."""
        return {"status": "ok"}

    return application


app = create_app()
