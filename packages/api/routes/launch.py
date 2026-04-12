"""Launch tracking and dashboard routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes._supabase import supabase_fetch, supabase_insert
from routes.admin_auth import require_admin_key
from services.launch_dashboard import SUPPORTED_WINDOWS, build_launch_dashboard

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


def _extract_destination_domain(destination_url: str) -> str:
    parsed = urlsplit(destination_url)
    if parsed.scheme not in ALLOWED_DESTINATION_SCHEMES:
        raise HTTPException(status_code=400, detail="Unsupported destination URL scheme.")

    if parsed.scheme == "mailto":
        address = parsed.path.rsplit("@", maxsplit=1)
        if len(address) != 2 or not address[1]:
            raise HTTPException(status_code=400, detail="Invalid mailto destination.")
        return address[1].lower()

    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Destination URL must include a hostname.")
    return parsed.netloc.lower()


@router.post("/clicks")
async def capture_click_event(body: ClickEventRequest, request: Request) -> dict:
    """Capture an outbound click event for launch tracking."""
    if body.event_type not in ALLOWED_CLICK_EVENTS:
        raise HTTPException(status_code=400, detail="Unsupported click event type.")

    destination_domain = _extract_destination_domain(body.destination_url)
    referer = request.headers.get("referer")

    payload = {
        "created_at": datetime.now(tz=UTC).isoformat(),
        "event_type": body.event_type,
        "service_slug": body.service_slug,
        "page_path": body.page_path,
        "destination_url": body.destination_url,
        "destination_domain": destination_domain,
        "source_surface": body.source_surface,
        "visitor_id": body.visitor_id,
        "session_id": body.session_id,
        "utm_source": body.utm_source,
        "utm_medium": body.utm_medium,
        "utm_campaign": body.utm_campaign,
        "utm_content": body.utm_content,
        "referrer_url": referer,
    }

    if not await supabase_insert("click_events", payload):
        raise HTTPException(status_code=503, detail="Click tracking unavailable.")

    return {"data": {"logged": True}, "error": None}


@router.get("/admin/launch/dashboard")
async def get_launch_dashboard(
    window: Literal["24h", "7d", "launch"] = Query(default="7d"),
    _: None = Depends(require_admin_key),
) -> dict:
    """Return the internal launch dashboard payload."""
    if window not in SUPPORTED_WINDOWS:
        raise HTTPException(status_code=400, detail="Unsupported dashboard window.")

    query_logs = await supabase_fetch(
        "query_logs?select=created_at,source,query_type,query_text,query_params,agent_id,user_agent"
        "&order=created_at.desc&limit=5000"
    )
    click_events = await supabase_fetch(
        "click_events?select=created_at,event_type,service_slug,destination_domain,source_surface,page_path"
        "&order=created_at.desc&limit=5000"
    )
    executions = await supabase_fetch(
        "capability_executions?select=executed_at,capability_id,success"
        "&order=executed_at.desc&limit=5000"
    )
    services = await supabase_fetch("services?select=slug")

    data = build_launch_dashboard(
        query_logs=query_logs or [],
        click_events=click_events or [],
        execution_rows=executions or [],
        service_rows=services or [],
        window=window,
    )
    return {"data": data, "error": None}
