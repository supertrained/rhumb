from __future__ import annotations

from routes.capabilities import (
    _credential_mode_map_fields,
    _mapped_configured_by_mode,
)


def test_managed_plus_byok_map_keeps_unconfigured_byok() -> None:
    assert _mapped_configured_by_mode(
        ["byo", "rhumb_managed"],
        byok_configured=False,
    ) == {
        "byok": False,
        "rhumb_managed": True,
    }
    assert _credential_mode_map_fields(
        ["byo", "rhumb_managed"],
        byok_configured=False,
    ) == {
        "credential_modes": ["byok", "rhumb_managed"],
        "configured_by_mode": {"byok": False, "rhumb_managed": True},
        "configured_credential_modes": ["rhumb_managed"],
    }


def test_agent_vault_stays_unconfigured_on_the_map() -> None:
    fields = _credential_mode_map_fields(
        ["byok", "agent_vault", "rhumb_managed"],
        byok_configured=True,
    )
    assert fields == {
        "credential_modes": ["byok", "agent_vault", "rhumb_managed"],
        "configured_by_mode": {
            "byok": True,
            "agent_vault": False,
            "rhumb_managed": True,
        },
        "configured_credential_modes": ["byok", "rhumb_managed"],
    }


def test_byok_only_index_engine_map_is_false_when_store_is_empty() -> None:
    assert _credential_mode_map_fields(
        ["byok"],
        byok_configured=False,
    ) == {
        "credential_modes": ["byok"],
        "configured_by_mode": {"byok": False},
        "configured_credential_modes": [],
    }
