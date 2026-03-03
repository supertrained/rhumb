"""Score, compare, evaluation, and alert route skeletons."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/services/{slug}/score")
async def get_score(slug: str) -> dict:
    """Get the latest AN score for a service."""
    return {"data": {"slug": slug, "score": None}, "error": None}


@router.get("/compare")
async def compare_services(services: str) -> dict:
    """Compare a comma-separated set of services."""
    requested = [service.strip() for service in services.split(",") if service.strip()]
    return {"data": {"services": requested, "comparison": []}, "error": None}


@router.post("/evaluate")
async def evaluate_stack() -> dict:
    """Evaluate an agent tool stack."""
    return {"data": {"accepted": True, "result": None}, "error": None}


@router.get("/alerts")
async def get_alerts() -> dict:
    """Fetch schema/score change alerts for authenticated users."""
    return {"data": {"alerts": []}, "error": None}
