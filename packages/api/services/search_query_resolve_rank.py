from __future__ import annotations

from enum import IntEnum

from services.service_slugs import public_service_slug

SEARCH_QUERY_CAPABILITY_ID = "search.query"

SEARCH_QUERY_BEACHHEAD_WEB_SEARCH = frozenset(
    {
        "exa",
        "tavily",
        "brave-search-api",
    }
)

SEARCH_QUERY_INDEX_ENGINES = frozenset(
    {
        "algolia",
        "elasticsearch",
        "meilisearch",
        "typesense",
    }
)

if not SEARCH_QUERY_BEACHHEAD_WEB_SEARCH.isdisjoint(SEARCH_QUERY_INDEX_ENGINES):
    raise RuntimeError("search.query beachhead and index-engine slug sets overlap")


class SearchQueryProviderClass(IntEnum):
    BEACHHEAD_WEB_SEARCH = 0
    OTHER = 1
    INDEX_ENGINE = 2


_RECOMMENDATION_RANK = {
    "preferred": 0,
    "available": 1,
    "caution": 2,
    "unscored": 3,
}


def search_query_provider_class(service_slug: str | None) -> SearchQueryProviderClass:
    slug = public_service_slug(service_slug) or str(service_slug or "").strip().lower()
    if slug in SEARCH_QUERY_BEACHHEAD_WEB_SEARCH:
        return SearchQueryProviderClass.BEACHHEAD_WEB_SEARCH
    if slug in SEARCH_QUERY_INDEX_ENGINES:
        return SearchQueryProviderClass.INDEX_ENGINE
    return SearchQueryProviderClass.OTHER


def resolve_provider_sort_key(
    capability_id: str,
    provider: dict[str, object],
) -> tuple[int, int, float]:
    recommendation = _RECOMMENDATION_RANK.get(str(provider.get("recommendation") or ""), 4)
    an_score = provider.get("an_score")
    negated_an = -(float(an_score) if an_score is not None else 0.0)
    if capability_id != SEARCH_QUERY_CAPABILITY_ID:
        return (0, recommendation, negated_an)
    return (
        int(search_query_provider_class(str(provider.get("service_slug") or ""))),
        recommendation,
        negated_an,
    )


def sort_resolve_providers(
    capability_id: str,
    providers: list[dict[str, object]],
) -> None:
    providers.sort(key=lambda provider: resolve_provider_sort_key(capability_id, provider))


def preferred_mapped_provider_slug(
    capability_id: str,
    mappings: list[dict[str, object]],
    scores_by_slug: dict[str, float],
) -> str | None:
    providers: list[dict[str, object]] = []
    seen: set[str] = set()
    for mapping in mappings:
        slug = (
            public_service_slug(mapping.get("service_slug"))
            or str(mapping.get("service_slug") or "").strip()
        )
        if not slug or slug in seen:
            continue
        seen.add(slug)
        providers.append(
            {
                "service_slug": slug,
                "an_score": scores_by_slug.get(slug),
                "recommendation": "available",
            }
        )
    if not providers:
        return None
    sort_resolve_providers(capability_id, providers)
    return (
        public_service_slug(providers[0].get("service_slug"))
        or str(providers[0].get("service_slug") or "")
        or None
    )
