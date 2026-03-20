"""FastAPI application factory and router registration."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from middleware.query_logging import QueryLoggingMiddleware
from services.x402 import PaymentRequiredException, payment_required_handler
from routes import (
    admin_agents,
    admin_billing,
    auth,
    billing,
    budget,
    capabilities,
    capability_execute,
    leaderboard,
    launch,
    pricing,
    probes,
    proxy,
    reviews,
    routing,
    scores,
    search,
    services,
    tester_fleet,
    webhooks,
)
from routes.admin_auth import require_admin_key

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Application lifespan: initialize async dependencies at startup."""
    # Initialize Supabase-backed stores up front so the HTTP control plane,
    # ACL/rate-limit path, and durable metering all point at the same identity source.
    from db.client import get_supabase_client
    from schemas.agent_identity import get_agent_identity_store
    from schemas.user import get_user_store
    from services.agent_usage_analytics import get_usage_analytics
    from services.operational_fact_emitter import get_operational_fact_emitter
    from services.proxy_auth import get_auth_injector
    from services.proxy_finalizer import get_proxy_finalizer
    from services.usage_metering import get_usage_meter_engine

    supabase = await get_supabase_client()
    get_agent_identity_store(supabase)
    logger.info("Agent identity: Supabase client initialized")

    get_user_store(supabase)
    logger.info("User store: Supabase client initialized")

    emitter = get_operational_fact_emitter(supabase)
    logger.info("Operational fact emitter: Supabase client initialized")

    get_auth_injector(emitter=emitter)
    logger.info("Auth injector: credential store warmed")

    meter = get_usage_meter_engine()
    if await meter.ensure_supabase():
        logger.info("Durable metering: Supabase client initialized")
    else:
        logger.warning("Durable metering: Supabase unavailable — using in-memory fallback")

    get_usage_analytics(supabase_client=supabase)
    logger.info("Agent usage analytics: Supabase client initialized")

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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://rhumb.dev",
            "https://www.rhumb.dev",
            "https://rhumb-orcin.vercel.app",
            "http://localhost:3000",
            "http://localhost:3001",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["X-Rhumb-Key", "X-Rhumb-Admin-Key", "Content-Type", "Authorization"],
    )
    application.add_middleware(QueryLoggingMiddleware)

    # ── Exception handlers ──
    application.add_exception_handler(PaymentRequiredException, payment_required_handler)

    # ── Routers ──
    application.include_router(capabilities.router, prefix="/v1", tags=["capabilities"])
    application.include_router(capability_execute.router, prefix="/v1", tags=["capability-execute"])
    application.include_router(services.router, prefix="/v1", tags=["services"])
    application.include_router(probes.router, prefix="/v1", tags=["probes"])
    application.include_router(scores.router, prefix="/v1", tags=["scores"])
    application.include_router(search.router, prefix="/v1", tags=["search"])
    application.include_router(leaderboard.router, prefix="/v1", tags=["leaderboard"])
    application.include_router(reviews.router, prefix="/v1", tags=["reviews"])
    application.include_router(launch.router, prefix="/v1", tags=["launch"])
    application.include_router(pricing.router, prefix="/v1", tags=["pricing"])
    application.include_router(
        tester_fleet.router, prefix="/v1", tags=["tester-fleet"],
        dependencies=[Depends(require_admin_key)],
    )
    application.include_router(budget.router, tags=["budget"])
    application.include_router(routing.router, tags=["routing"])
    application.include_router(proxy.router, prefix="/v1/proxy", tags=["proxy"])
    application.include_router(
        proxy.admin_router, prefix="/v1", tags=["schema-admin"],
        dependencies=[Depends(require_admin_key)],
    )
    application.include_router(
        admin_agents.router, prefix="/v1/admin", tags=["admin-agents"],
        dependencies=[Depends(require_admin_key)],
    )
    application.include_router(
        admin_billing.router, prefix="/v1", tags=["admin-billing"],
        dependencies=[Depends(require_admin_key)],
    )
    application.include_router(billing.router, prefix="/v1", tags=["billing"])
    application.include_router(auth.router, prefix="/v1", tags=["auth"])
    application.include_router(webhooks.router, tags=["webhooks"])

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Simple liveness endpoint."""
        return {"status": "ok"}

    return application


app = create_app()
