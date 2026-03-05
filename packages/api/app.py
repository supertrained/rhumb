"""FastAPI application factory and router registration."""

from fastapi import FastAPI

from routes import leaderboard, probes, scores, search, services, tester_fleet


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Rhumb API", version="0.0.1")
    application.include_router(services.router, prefix="/v1", tags=["services"])
    application.include_router(probes.router, prefix="/v1", tags=["probes"])
    application.include_router(scores.router, prefix="/v1", tags=["scores"])
    application.include_router(search.router, prefix="/v1", tags=["search"])
    application.include_router(leaderboard.router, prefix="/v1", tags=["leaderboard"])
    application.include_router(tester_fleet.router, prefix="/v1", tags=["tester-fleet"])

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Simple liveness endpoint."""
        return {"status": "ok"}

    return application


app = create_app()
