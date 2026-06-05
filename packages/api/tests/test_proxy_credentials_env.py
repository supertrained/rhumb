from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.proxy_credentials import CredentialStore


def test_ipinfo_loader_accepts_live_migration_env_name(monkeypatch) -> None:
    """Hosted Resolve uses RHUMB_CREDENTIAL_IPINFO_TOKEN from the DB-backed config."""
    monkeypatch.delenv("RHUMB_CREDENTIAL_IPINFO_API_TOKEN", raising=False)
    monkeypatch.setenv("RHUMB_CREDENTIAL_IPINFO_TOKEN", "ipinfo_live_token")

    store = CredentialStore(auto_load=False)
    store._load_from_env("ipinfo")

    assert store.get_credential("ipinfo", "bearer_token") == "ipinfo_live_token"
    assert "ipinfo" in store.callable_services()


def test_dynamic_lookup_accepts_ipinfo_migration_env_alias(monkeypatch) -> None:
    monkeypatch.delenv("RHUMB_CREDENTIAL_IPINFO_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("RHUMB_CREDENTIAL_IPINFO_API_TOKEN", raising=False)
    monkeypatch.setenv("RHUMB_CREDENTIAL_IPINFO_TOKEN", "ipinfo_alias_token")

    store = CredentialStore(auto_load=False)

    assert store.get_credential("ipinfo", "bearer_token") == "ipinfo_alias_token"


def test_resend_and_google_places_envs_are_first_class(monkeypatch) -> None:
    monkeypatch.setenv("RHUMB_CREDENTIAL_RESEND_API_KEY", "resend_live_key")
    monkeypatch.setenv("RHUMB_CREDENTIAL_GOOGLE_PLACES_API_KEY", "google_places_live_key")

    store = CredentialStore(auto_load=False)
    store._load_from_env("resend")
    store._load_from_env("google-maps")
    store._load_from_env("google-places")

    assert store.get_credential("resend", "api_key") == "resend_live_key"
    assert store.get_credential("google-maps", "api_key") == "google_places_live_key"
    assert store.get_credential("google-places", "api_key") == "google_places_live_key"
