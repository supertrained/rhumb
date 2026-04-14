"""Regression coverage for the example /resolve helper logic."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "examples" / "resolve_helpers.py"
    spec = importlib.util.spec_from_file_location("resolve_helpers", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


resolve_helpers = _load_module()


def test_execute_ready_provider_slugs_prefers_execute_hint_over_ranked_rows() -> None:
    payload = {
        "providers": [
            {"service_slug": "resend", "available_for_execute": False, "endpoint_pattern": "/emails"},
            {"service_slug": "sendgrid", "available_for_execute": True, "endpoint_pattern": "/v3/mail/send"},
            {"service_slug": "amazon-ses", "available_for_execute": True, "endpoint_pattern": "/v2/email/outbound-emails"},
        ],
        "fallback_chain": ["sendgrid", "amazon-ses"],
        "execute_hint": {
            "preferred_provider": "sendgrid",
            "fallback_providers": ["amazon-ses"],
        },
    }

    assert resolve_helpers.execute_ready_provider_slugs(payload) == ["sendgrid", "amazon-ses"]
    assert resolve_helpers.preferred_execute_provider(payload) == "sendgrid"


def test_execute_ready_provider_slugs_falls_back_to_fallback_chain() -> None:
    payload = {
        "providers": [
            {"service_slug": "resend", "available_for_execute": False, "endpoint_pattern": "/emails"},
            {"service_slug": "sendgrid", "available_for_execute": True, "endpoint_pattern": "/v3/mail/send"},
        ],
        "fallback_chain": ["sendgrid"],
    }

    assert resolve_helpers.execute_ready_provider_slugs(payload) == ["sendgrid"]
    assert resolve_helpers.preferred_execute_provider(payload) == "sendgrid"


def test_execute_ready_provider_slugs_returns_empty_when_only_recovery_remains() -> None:
    payload = {
        "providers": [
            {"service_slug": "resend", "available_for_execute": False, "endpoint_pattern": "/emails"},
            {"service_slug": "postmark", "available_for_execute": True, "endpoint_pattern": None},
        ],
        "fallback_chain": [],
        "execute_hint": None,
        "recovery_hint": {
            "reason": "no_execute_ready_providers",
            "resolve_url": "/v1/capabilities/email.send/resolve",
            "unavailable_provider_slugs": ["resend"],
            "not_execute_ready_provider_slugs": ["postmark"],
            "supported_provider_slugs": ["resend", "postmark"],
        },
    }

    assert resolve_helpers.execute_ready_provider_slugs(payload) == []
    assert resolve_helpers.preferred_execute_provider(payload) is None
    assert resolve_helpers.recovery_resolve_url(payload) == "/v1/capabilities/email.send/resolve"
    assert resolve_helpers.recovery_credential_modes_url(payload) is None
    assert resolve_helpers.describe_recovery_hint(payload) == (
        "no_execute_ready_providers; resolve_url=/v1/capabilities/email.send/resolve; unavailable=resend; "
        "not_execute_ready=postmark; supported=resend,postmark"
    )


def test_describe_recovery_hint_surfaces_alternate_execute_handoff() -> None:
    payload = {
        "recovery_hint": {
            "reason": "no_providers_match_credential_mode",
            "resolve_url": "/v1/capabilities/email.send/resolve",
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "supported_provider_slugs": ["resend", "gmail"],
            "alternate_execute_hint": {
                "preferred_provider": "gmail",
                "preferred_credential_mode": "agent_vault",
                "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
                "setup_url": "/v1/services/gmail/ceremony",
            },
        },
    }

    assert resolve_helpers.preferred_recovery_handoff(payload) == (
        "alternate_execute",
        {
            "preferred_provider": "gmail",
            "preferred_credential_mode": "agent_vault",
            "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
            "setup_url": "/v1/services/gmail/ceremony",
        },
    )
    assert resolve_helpers.recovery_resolve_url(payload) == "/v1/capabilities/email.send/resolve"
    assert resolve_helpers.recovery_credential_modes_url(payload) == "/v1/capabilities/email.send/credential-modes"
    assert resolve_helpers.describe_recovery_hint(payload) == (
        "no_providers_match_credential_mode; resolve_url=/v1/capabilities/email.send/resolve; "
        "credential_modes_url=/v1/capabilities/email.send/credential-modes; supported=resend,gmail; "
        "alternate_execute=gmail(agent_vault); "
        "alternate_execute_endpoint=POST /gmail/v1/users/me/messages/send; "
        "alternate_execute_setup_url=/v1/services/gmail/ceremony"
    )



def test_describe_recovery_hint_surfaces_setup_handoff() -> None:
    payload = {
        "recovery_hint": {
            "reason": "no_execute_ready_providers",
            "resolve_url": "/v1/capabilities/email.send/resolve",
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "not_execute_ready_provider_slugs": ["resend"],
            "setup_handoff": {
                "preferred_provider": "resend",
                "preferred_credential_mode": "byok",
                "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
            },
        },
    }

    assert resolve_helpers.preferred_recovery_handoff(payload) == (
        "setup_handoff",
        {
            "preferred_provider": "resend",
            "preferred_credential_mode": "byok",
            "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
        },
    )
    assert resolve_helpers.recovery_resolve_url(payload) == "/v1/capabilities/email.send/resolve"
    assert resolve_helpers.recovery_credential_modes_url(payload) == "/v1/capabilities/email.send/credential-modes"
    assert resolve_helpers.describe_recovery_hint(payload) == (
        "no_execute_ready_providers; resolve_url=/v1/capabilities/email.send/resolve; "
        "credential_modes_url=/v1/capabilities/email.send/credential-modes; not_execute_ready=resend; "
        "setup_handoff=resend(byok); "
        "setup_handoff_setup_hint=Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials"
    )



def test_preferred_recovery_handoff_prefers_alternate_execute_over_setup() -> None:
    payload = {
        "recovery_hint": {
            "alternate_execute_hint": {
                "preferred_provider": "gmail",
                "preferred_credential_mode": "agent_vault",
            },
            "setup_handoff": {
                "preferred_provider": "resend",
                "preferred_credential_mode": "byok",
            },
        },
    }

    assert resolve_helpers.preferred_recovery_handoff(payload) == (
        "alternate_execute",
        {
            "preferred_provider": "gmail",
            "preferred_credential_mode": "agent_vault",
        },
    )
