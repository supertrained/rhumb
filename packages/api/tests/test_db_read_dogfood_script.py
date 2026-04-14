"""Tests for the DB read dogfood script resolve-handoff surfacing."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "db_read_dogfood.py"

spec = importlib.util.spec_from_file_location("db_read_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
db_read_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db_read_dogfood)


def test_resolve_handoff_prefers_execute_hint() -> None:
    handoff = db_read_dogfood._resolve_handoff(
        {
            "data": {
                "execute_hint": {
                    "preferred_provider": "postgresql",
                    "preferred_credential_mode": "agent_vault",
                    "selection_reason": "highest_ranked_provider",
                    "setup_hint": "Pass X-Agent-Token",
                    "credential_modes_url": "/v1/capabilities/db.query.read/credential-modes",
                    "setup_url": "/v1/services/postgresql/ceremony",
                    "configured": False,
                }
            }
        }
    )

    assert handoff == {
        "source": "execute_hint",
        "preferred_provider": "postgresql",
        "preferred_credential_mode": "agent_vault",
        "selection_reason": "highest_ranked_provider",
        "setup_hint": "Pass X-Agent-Token",
        "credential_modes_url": "/v1/capabilities/db.query.read/credential-modes",
        "setup_url": "/v1/services/postgresql/ceremony",
        "configured": False,
    }


def test_resolve_handoff_falls_back_to_recovery_setup_handoff() -> None:
    handoff = db_read_dogfood._resolve_handoff(
        {
            "data": {
                "execute_hint": None,
                "recovery_hint": {
                    "reason": "no_providers_match_credential_mode",
                    "resolve_url": "/v1/capabilities/db.query.read/resolve",
                    "credential_modes_url": "/v1/capabilities/db.query.read/credential-modes",
                    "setup_handoff": {
                        "preferred_provider": "postgresql",
                        "preferred_credential_mode": "agent_vault",
                        "selection_reason": "highest_ranked_provider",
                        "setup_hint": "Pass X-Agent-Token",
                        "setup_url": "/v1/services/postgresql/ceremony",
                        "configured": False,
                    },
                },
            }
        }
    )

    assert handoff == {
        "source": "setup_handoff",
        "reason": "no_providers_match_credential_mode",
        "resolve_url": "/v1/capabilities/db.query.read/resolve",
        "preferred_provider": "postgresql",
        "preferred_credential_mode": "agent_vault",
        "selection_reason": "highest_ranked_provider",
        "setup_hint": "Pass X-Agent-Token",
        "setup_url": "/v1/services/postgresql/ceremony",
        "credential_modes_url": "/v1/capabilities/db.query.read/credential-modes",
        "configured": False,
    }


def test_failure_summary_includes_next_step_handoff() -> None:
    summary = db_read_dogfood._failure_summary(
        "execute db.query.read failed: missing token",
        {
            "capabilities": {
                "db.query.read": {
                    "resolve_handoff": {
                        "source": "execute_hint",
                        "preferred_provider": "postgresql",
                        "preferred_credential_mode": "agent_vault",
                        "selection_reason": "highest_ranked_provider",
                        "setup_url": "/v1/services/postgresql/ceremony",
                    }
                }
            }
        },
    )

    assert summary == (
        "execute db.query.read failed: missing token; "
        "Resolve next step: source=execute_hint, provider=postgresql, mode=agent_vault, "
        "selection_reason=highest_ranked_provider, setup_url=/v1/services/postgresql/ceremony"
    )


def test_attach_resolve_step_promotes_handoff_to_top_level_failed_payload() -> None:
    payload = db_read_dogfood._attach_resolve_step(
        {
            "ok": False,
            "summary": "execute db.query.read failed: missing token",
            "capabilities": {
                "db.query.read": {
                    "resolve_handoff": {
                        "source": "setup_handoff",
                        "preferred_provider": "postgresql",
                        "preferred_credential_mode": "agent_vault",
                        "setup_url": "/v1/services/postgresql/ceremony",
                    }
                }
            },
        }
    )

    assert payload["resolve_step"] == (
        "Resolve next step: source=setup_handoff, provider=postgresql, mode=agent_vault, "
        "setup_url=/v1/services/postgresql/ceremony"
    )
