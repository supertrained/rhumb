"""Launch tracking and dashboard routes."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes._supabase import supabase_fetch, supabase_insert
from routes.admin_auth import require_launch_dashboard_access
from services.error_envelope import RhumbError
from services.launch_dashboard import SUPPORTED_WINDOWS, build_launch_dashboard
from services.service_slugs import public_service_slug

router = APIRouter(tags=["launch"])

ALLOWED_CLICK_EVENTS = {
    "provider_click",
    "docs_click",
    "dispute_click",
    "github_dispute_click",
    "contact_click",
}
ALLOWED_DESTINATION_SCHEMES = {"http", "https", "mailto"}


class ClickEventRequest(BaseModel):
    """Client payload for outbound click capture."""

    event_type: str = Field(...)
    destination_url: str = Field(...)
    service_slug: str | None = Field(default=None)
    page_path: str | None = Field(default=None)
    source_surface: str = Field(default="unknown")
    visitor_id: str | None = Field(default=None)
    session_id: str | None = Field(default=None)
    utm_source: str | None = Field(default=None)
    utm_medium: str | None = Field(default=None)
    utm_campaign: str | None = Field(default=None)
    utm_content: str | None = Field(default=None)


def _validated_dashboard_window(window: str) -> str:
    normalized = str(window or "").strip().lower()
    if normalized in SUPPORTED_WINDOWS:
        return normalized

    allowed = ", ".join(sorted(SUPPORTED_WINDOWS))
    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'window' filter.",
        detail=f"Use one of: {allowed}.",
    )


def _validated_click_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip().lower()
    if normalized in ALLOWED_CLICK_EVENTS:
        return normalized

    raise RhumbError(
        "INVALID_PARAMETERS",
        message="Invalid 'event_type' field.",
        detail=f"Use one of: {', '.join(sorted(ALLOWED_CLICK_EVENTS))}.",
    )


def _normalized_optional_click_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _extract_destination_domain(destination_url: str) -> str:
    parsed = urlsplit(destination_url.strip())
    if parsed.scheme not in ALLOWED_DESTINATION_SCHEMES:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'destination_url' field.",
            detail="Use an http, https, or mailto destination URL.",
        )

    if parsed.scheme == "mailto":
        address = parsed.path.rsplit("@", maxsplit=1)
        if len(address) != 2 or not address[1]:
            raise RhumbError(
                "INVALID_PARAMETERS",
                message="Invalid 'destination_url' field.",
                detail="Use a valid mailto destination with a recipient domain.",
            )
        return address[1].lower()

    if not parsed.netloc:
        raise RhumbError(
            "INVALID_PARAMETERS",
            message="Invalid 'destination_url' field.",
            detail="HTTP destination URLs must include a hostname.",
        )
    return parsed.netloc.lower()


@router.post("/clicks")
async def capture_click_event(body: ClickEventRequest, request: Request) -> dict:
    """Capture an outbound click event for launch tracking."""
    event_type = _validated_click_event_type(body.event_type)
    destination_url = str(body.destination_url or "").strip()
    destination_domain = _extract_destination_domain(destination_url)
    referer = request.headers.get("referer")

    normalized_service_slug = public_service_slug(body.service_slug)
    if normalized_service_slug is None and isinstance(body.service_slug, str):
        normalized_service_slug = body.service_slug.strip().lower() or None
    source_surface = _normalized_optional_click_text(body.source_surface) or "unknown"

    payload = {
        "created_at": datetime.now(tz=UTC).isoformat(),
        "event_type": event_type,
        "service_slug": normalized_service_slug,
        "page_path": _normalized_optional_click_text(body.page_path),
        "destination_url": destination_url,
        "destination_domain": destination_domain,
        "source_surface": source_surface,
        "visitor_id": _normalized_optional_click_text(body.visitor_id),
        "session_id": _normalized_optional_click_text(body.session_id),
        "utm_source": _normalized_optional_click_text(body.utm_source),
        "utm_medium": _normalized_optional_click_text(body.utm_medium),
        "utm_campaign": _normalized_optional_click_text(body.utm_campaign),
        "utm_content": _normalized_optional_click_text(body.utm_content),
        "referrer_url": referer,
    }

    if not await supabase_insert("click_events", payload):
        raise HTTPException(status_code=503, detail="Click tracking unavailable.")

    return {"data": {"logged": True}, "error": None}


@router.get("/admin/launch/dashboard")
async def get_launch_dashboard(
    window: str = Query(default="7d"),
    _: None = Depends(require_launch_dashboard_access),
) -> dict:
    """Return the internal launch dashboard payload."""
    effective_window = _validated_dashboard_window(window)

    query_logs = await supabase_fetch(
        "query_logs?select=created_at,source,query_type,query_text,query_params,agent_id,user_agent"
        "&order=created_at.desc&limit=5000"
    )
    click_events = await supabase_fetch(
        "click_events?select=created_at,event_type,service_slug,destination_domain,source_surface,page_path"
        "&order=created_at.desc&limit=5000"
    )
    executions = await supabase_fetch(
        "capability_executions?select=executed_at,capability_id,success,agent_id,interface,credential_mode"
        "&order=executed_at.desc&limit=5000"
    )
    services = await supabase_fetch("services?select=slug")

    data = build_launch_dashboard(
        query_logs=query_logs or [],
        click_events=click_events or [],
        execution_rows=executions or [],
        service_rows=services or [],
        window=effective_window,
    )
    return {"data": data, "error": None}
