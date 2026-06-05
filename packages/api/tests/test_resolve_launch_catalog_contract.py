"""Launch-catalog contract tests for the Rhumb-managed public P0 surface."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from routes.proxy import SERVICE_REGISTRY
from services.proxy_auth import AuthInjector
from services.proxy_credentials import _ENV_FALLBACK
from services.service_slugs import normalize_proxy_slug


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "resolve_launch_catalog_smoke.py"


def _load_catalog_module():
    spec = importlib.util.spec_from_file_location("resolve_launch_catalog_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0_launch_catalog_has_expected_capability_set() -> None:
    module = _load_catalog_module()

    assert set(module.P0_CATALOG) == {
        "search.query",
        "scrape.extract",
        "ai.generate_text",
        "ai.generate_image",
        "data.enrich_person",
        "data.enrich_company",
        "geo.lookup",
        "maps.places_search",
    }


def test_p0_launch_catalog_providers_have_proxy_auth_and_env_fallbacks() -> None:
    module = _load_catalog_module()

    expected_providers = {spec["provider"] for spec in module.P0_CATALOG.values()}
    for provider in expected_providers:
        proxy_provider = normalize_proxy_slug(provider)
        assert proxy_provider in SERVICE_REGISTRY
        assert proxy_provider in _ENV_FALLBACK
        assert AuthInjector.default_method_for(proxy_provider) is not None


def test_p0_launch_catalog_keeps_person_enrichment_on_proof_substitute() -> None:
    module = _load_catalog_module()

    assert module.P0_CATALOG["data.enrich_person"]["execution_policy"] == "proof_substitute"
    assert "consented" in module.P0_CATALOG["data.enrich_person"]["proof_substitute"]


def test_external_write_and_missing_provider_surfaces_are_deferred() -> None:
    module = _load_catalog_module()

    assert "email.send" in module.DEFERRED_CAPABILITIES
    assert "email.verify" in module.DEFERRED_CAPABILITIES
    assert "sendgrid" in module.DEFERRED_CAPABILITIES
    assert "External-write" in module.DEFERRED_CAPABILITIES["email.send"]
    assert "RHUMB_CREDENTIAL_SENDGRID_API_KEY" in module.DEFERRED_CAPABILITIES["sendgrid"]
