"""Index score is not an execute grant.

``GET /v1/proxy/services`` already flags each registered slug with
``callable``. Index service, score, and search payloads repeat that fact
next to ``an_score`` / ``execution_score`` so operators do not treat a
high Index score as Rhumb execute.
"""

from __future__ import annotations

from services.proxy_credentials import get_credential_store
from services.service_slugs import canonicalize_service_slug, public_service_slug

CALLABLE_URL = "/v1/proxy/services"


def public_callable_slugs() -> set[str]:
    slugs: set[str] = set()
    for service in get_credential_store().callable_services():
        slug = public_service_slug(service) or canonicalize_service_slug(str(service).strip())
        if slug:
            slugs.add(slug)
    return slugs


def index_callable_fields(
    service_slug: str | None,
    callable_slugs: set[str] | None = None,
) -> dict[str, bool | str]:
    slug = public_service_slug(service_slug) or str(service_slug or "").strip().lower()
    known = public_callable_slugs() if callable_slugs is None else callable_slugs
    return {
        "callable": bool(slug) and slug in known,
        "callable_url": CALLABLE_URL,
    }
