"""Shared fixtures for API tests."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set admin secret before importing app (config reads env at import time)
ADMIN_TEST_SECRET = "rhumb_test_admin_secret_0000"
os.environ.setdefault("RHUMB_ADMIN_SECRET", ADMIN_TEST_SECRET)

from app import app

# ── Bypass auth constants (shared across all proxy test files) ───────────────
BYPASS_KEY = "rhumb_test_bypass_key_0000"
BYPASS_AGENT_ID = "00000000-0000-0000-0000-bypass000001"
_VAULT_STRIPE_KEY = "sk_test_vault_injected"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def bypass_agent_id() -> str:
    """Return the fixed bypass agent_id used by _inject_proxy_bypass_auth."""
    return BYPASS_AGENT_ID


@pytest.fixture(autouse=True)
def _inject_proxy_bypass_auth() -> Generator[None, None, None]:
    """Inject control-plane singletons into proxy module for all tests.

    This allows tests that don't explicitly manage identity/ACL/metering
    to pass without wiring up real auth. Tests that manage their own
    singletons (e.g. test_proxy_auth_wiring.py via _reset_singletons)
    will clear and replace these after this fixture runs.

    Uses a fixed BYPASS_AGENT_ID constant so integration tests can pre-seed
    breakers and assert on latency records without dynamic UUID resolution.
    """
    import routes.proxy as proxy_module
    from schemas.agent_identity import AgentIdentityStore, hash_api_key, reset_identity_store
    from services.agent_access_control import AgentAccessControl, reset_agent_access_control
    from services.agent_rate_limit import AgentRateLimitChecker, reset_agent_rate_limit_checker
    from services.operational_fact_emitter import reset_operational_fact_emitter
    from services.proxy_credentials import CredentialStore
    from services.proxy_auth import AuthInjector
    from services.usage_metering import UsageMeterEngine, reset_usage_meter_engine
    import json
    from datetime import datetime, timezone

    identity_store = AgentIdentityStore(supabase_client=None)
    # Inject bypass agent directly with a fixed ID (avoids UUID randomness in assertions)
    now = datetime.now(timezone.utc).isoformat()
    identity_store._mem_agents[BYPASS_AGENT_ID] = {
        "agent_id": BYPASS_AGENT_ID,
        "name": "test-bypass",
        "organization_id": "org-test",
        "api_key_hash": hash_api_key(BYPASS_KEY),
        "api_key_prefix": BYPASS_KEY[:12],
        "api_key_created_at": now,
        "api_key_rotated_at": None,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "disabled_at": None,
        "rate_limit_qpm": 100,
        "timeout_seconds": 30,
        "retry_policy": json.dumps({"max_retries": 3, "backoff_ms": 100}),
        "description": "Test bypass agent",
        "tags": json.dumps([]),
        "custom_attributes": json.dumps({}),
    }
    identity_store._key_index[hash_api_key(BYPASS_KEY)] = BYPASS_AGENT_ID
    for svc in ("stripe", "slack", "github", "twilio", "sendgrid"):
        _run(identity_store.grant_service_access(BYPASS_AGENT_ID, svc))

    cred_store = CredentialStore(auto_load=False)
    cred_store.set_credential("stripe", "api_key", _VAULT_STRIPE_KEY)
    cred_store.set_credential("slack", "oauth_token", "xoxb-test-vault")
    cred_store.set_credential("github", "api_token", "ghp_test_vault")
    cred_store.set_credential("sendgrid", "api_key", "SG.test_vault")

    auth_injector = AuthInjector(cred_store)
    acl = AgentAccessControl(identity_store=identity_store)
    # Use a fresh RateLimiter per test to avoid cross-test counter accumulation
    from services.proxy_rate_limit import RateLimiter
    rate_checker = AgentRateLimitChecker(
        identity_store=identity_store, rate_limiter=RateLimiter()
    )
    meter = UsageMeterEngine(identity_store=identity_store)

    proxy_module._identity_store = identity_store
    proxy_module._acl_instance = acl
    proxy_module._rate_checker_instance = rate_checker
    proxy_module._auth_injector_instance = auth_injector
    proxy_module._meter_instance = meter
    reset_operational_fact_emitter()

    yield

    proxy_module._identity_store = None
    proxy_module._acl_instance = None
    proxy_module._rate_checker_instance = None
    proxy_module._auth_injector_instance = None
    proxy_module._meter_instance = None
    reset_identity_store()
    reset_agent_access_control()
    reset_agent_rate_limit_checker()
    reset_usage_meter_engine()
    reset_operational_fact_emitter()


@pytest.fixture
def client() -> TestClient:
    """Create an in-process FastAPI test client with bypass auth + admin headers."""
    return TestClient(app, headers={
        "X-Rhumb-Key": BYPASS_KEY,
        "X-Rhumb-Admin-Key": ADMIN_TEST_SECRET,
    })
