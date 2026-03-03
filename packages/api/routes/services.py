"""Service-related route skeletons."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/services")
async def list_services(limit: int = 20, offset: int = 0) -> dict:
    """List indexed services."""
    return {"data": {"items": [], "limit": limit, "offset": offset}, "error": None}


@router.get("/services/{slug}")
async def get_service(slug: str) -> dict:
    """Fetch a service profile by slug."""
    return {"data": {"slug": slug}, "error": None}


@router.get("/services/{slug}/failures")
async def get_failures(slug: str) -> dict:
    """Fetch active failure modes for a service."""
    return {"data": {"slug": slug, "failures": []}, "error": None}


@router.get("/services/{slug}/history")
async def get_history(slug: str) -> dict:
    """Fetch historical AN score entries for a service."""
    return {"data": {"slug": slug, "history": []}, "error": None}


@router.get("/services/{slug}/schema")
async def get_schema(slug: str) -> dict:
    """Fetch the latest schema snapshot for a service."""
    return {"data": {"slug": slug, "schema": None}, "error": None}


@router.post("/services/{slug}/report")
async def report_failure(slug: str) -> dict:
    """Submit a failure report for a service."""
    return {"data": {"slug": slug, "accepted": True}, "error": None}
