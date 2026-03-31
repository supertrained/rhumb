"""FastAPI application factory and router registration."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from cors import ALLOWED_CORS_ORIGINS
from middleware.error_response import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from middleware.query_logging import QueryLoggingMiddleware
from middleware.rate_limit import RateLimitMiddleware
from middleware.request_id import RequestIDMiddleware
from routes import (
    admin_agents,
    admin_billing,
    admin_budgets,
    auth,
    auth_wallet,
    billing,
    billing_v2,
    budget,
    capabilities,
    capability_execute,
    wallet_topup,
    leaderboard,
    launch,
    pricing,
    probes,
    proxy,
    explanations_v2,
    providers_v2,
    receipts_v2,
    recipes_v2,
    resolve_v2,
    reviews,
    routing,
    scores,
    scores_v2,
    search,
    services,
    status,
    telemetry,
    tester_fleet,
    trust_v2,
    webhooks,
)
from routes import audit_v2
from routes.admin_auth import require_admin_key
from services.x402 import PaymentRequiredException, payment_required_handler


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all API responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

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
    from services.email_otp import get_email_otp_service
    from services.operational_fact_emitter import get_operational_fact_emitter
    from services.proxy_auth import get_auth_injector
    from services.proxy_finalizer import get_proxy_finalizer
    from services.usage_metering import get_usage_meter_engine

    supabase = await get_supabase_client()
    get_agent_identity_store(supabase)
    logger.info("Agent identity: Supabase client initialized")

    get_user_store(supabase)
    logger.info("User store: Supabase client initialized")

    get_email_otp_service(supabase)
    logger.info("Email OTP service: Supabase client initialized")

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

    # Score cache auto-refresh (WU-41.4 structural separation)
    from services.score_cache import start_score_cache_refresh, stop_score_cache_refresh
    await start_score_cache_refresh()
    logger.info("Score cache refresh worker started")

    try:
        yield
    finally:
        await stop_score_cache_refresh()
        logger.info("Score cache refresh worker stopped")
        await proxy_finalizer.stop(drain=True)
        logger.info("Proxy finalizer worker drained")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Disable interactive docs and OpenAPI schema on production.
    # These expose the full attack surface to adversaries.
    is_prod = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
    application = FastAPI(
        title="Rhumb API",
        version="0.0.1",
        lifespan=_lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # ── Middleware ──
    application.add_middleware(QueryLoggingMiddleware)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=[
            "X-Rhumb-Key",
            "X-Rhumb-Admin-Key",
            "X-Payment",
            "PAYMENT-SIGNATURE",
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "X-Rhumb-Version",
            "X-Rhumb-Idempotency-Key",
            "X-Rhumb-Agent-Id",
            "X-Rhumb-Budget-Token",
        ],
        expose_headers=[
            "X-Request-ID",
            "X-Payment",
            "PAYMENT-RESPONSE",
            "X-Payment-Response",
            "X-Rhumb-Auth",
            "X-Rhumb-Wallet",
            "X-Rhumb-Rate-Remaining",
            "X-Rhumb-Version",
            "X-Rhumb-Compat",
        ],
    )

    # ── Exception handlers ──
    # Standardized error envelope: request_id + resolution on every error
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
    # x402 payment-required has its own handler (returns 402 with payment envelope)
    application.add_exception_handler(PaymentRequiredException, payment_required_handler)
    # Resolve v2 canonical error envelope handler
    from services.error_envelope import RhumbError, rhumb_error_handler
    application.add_exception_handler(RhumbError, rhumb_error_handler)

    # ── Routers ──
    application.include_router(capabilities.router, prefix="/v1", tags=["capabilities"])
    application.include_router(capability_execute.router, prefix="/v1", tags=["capability-execute"])
    application.include_router(resolve_v2.router, prefix="/v2", tags=["resolve-v2"])
    application.include_router(providers_v2.router, prefix="/v2", tags=["providers-v2"])
    application.include_router(receipts_v2.router, prefix="/v2", tags=["receipts-v2"])
    application.include_router(recipes_v2.router, prefix="/v2", tags=["recipes-v2"])
    application.include_router(explanations_v2.router, prefix="/v2", tags=["explanations-v2"])
    application.include_router(services.router, prefix="/v1", tags=["services"])
    application.include_router(probes.router, prefix="/v1", tags=["probes"])
    application.include_router(scores.router, prefix="/v1", tags=["scores"])
    application.include_router(scores_v2.router, tags=["scores-v2"])
    application.include_router(search.router, prefix="/v1", tags=["search"])
    application.include_router(leaderboard.router, prefix="/v1", tags=["leaderboard"])
    application.include_router(reviews.router, prefix="/v1", tags=["reviews"])
    application.include_router(launch.router, prefix="/v1", tags=["launch"])
    application.include_router(pricing.router, prefix="/v1", tags=["pricing"])
    application.include_router(telemetry.router, prefix="/v1", tags=["telemetry"])
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
    application.include_router(admin_budgets.router, tags=["admin-budgets"])
    application.include_router(billing.router, prefix="/v1", tags=["billing"])
    application.include_router(billing_v2.router, tags=["billing-v2"])
    application.include_router(trust_v2.router, tags=["trust-v2"])
    application.include_router(audit_v2.router, tags=["audit-v2"])
    application.include_router(status.router, prefix="/v1", tags=["status"])
    application.include_router(auth.router, prefix="/v1", tags=["auth"])
    application.include_router(auth_wallet.router, prefix="/v1", tags=["wallet-auth"])
    application.include_router(wallet_topup.router, prefix="/v1", tags=["wallet-topup"])
    application.include_router(webhooks.router, tags=["webhooks"])

    @application.get("/healthz")
    @application.get("/v1/healthz")
    async def healthz() -> dict[str, str]:
        """Simple liveness endpoint."""
        return {"status": "ok"}

    return application


app = create_app()
