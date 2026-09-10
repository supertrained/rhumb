from __future__ import annotations

from services.service_slugs import (
    canonicalize_service_slug,
    normalize_proxy_slug,
    public_service_slug,
    public_service_slug_candidates,
)


def test_public_service_slug_aliases_bare_brave_to_brave_search_api() -> None:
    assert public_service_slug("brave") == "brave-search-api"
    assert public_service_slug("BRAVE") == "brave-search-api"
    assert public_service_slug(" Brave ") == "brave-search-api"
    assert canonicalize_service_slug("brave") == "brave-search-api"


def test_public_service_slug_keeps_existing_proxy_and_canonical_ids() -> None:
    assert public_service_slug("brave-search") == "brave-search-api"
    assert public_service_slug("brave-search-api") == "brave-search-api"
    assert public_service_slug("pdl") == "people-data-labs"
    assert public_service_slug("people-data-labs") == "people-data-labs"


def test_public_service_slug_candidates_for_bare_brave_include_canonical_and_proxy() -> None:
    assert public_service_slug_candidates("brave") == [
        "brave-search-api",
        "brave",
        "brave-search",
    ]


def test_normalize_proxy_slug_keeps_brave_search_as_runtime_name() -> None:
    assert normalize_proxy_slug("brave-search-api") == "brave-search"
    assert normalize_proxy_slug("brave") == "brave"


def test_canonicalize_service_text_preserves_brave_brand_word() -> None:
    from routes.services import _canonicalize_service_text

    assert (
        _canonicalize_service_text("Brave Search", "brave-search-api", "brave-search-api")
        == "Brave Search"
    )
