"""FastAPI application factory and router registration."""

from fastapi import FastAPI

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


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Rhumb API", version="0.0.1")
    application.include_router(services.router, prefix="/v1", tags=["services"])
    application.include_router(probes.router, prefix="/v1", tags=["probes"])
    application.include_router(scores.router, prefix="/v1", tags=["scores"])
    application.include_router(search.router, prefix="/v1", tags=["search"])
    application.include_router(leaderboard.router, prefix="/v1", tags=["leaderboard"])
    application.include_router(tester_fleet.router, prefix="/v1", tags=["tester-fleet"])
    application.include_router(proxy.router, prefix="/v1/proxy", tags=["proxy"])
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
