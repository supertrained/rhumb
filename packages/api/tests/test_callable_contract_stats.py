"""Lock TestClient proxy_stats registered slugs to the committed callable contract."""

from __future__ import annotations

import json
from pathlib import Path


CONTRACT_JSON = Path(__file__).resolve().parents[3] / "docs" / "callable-contract.json"


def test_proxy_stats_registered_slugs_match_committed_contract(client):
    contract = json.loads(CONTRACT_JSON.read_text())
    registered = contract["services_registered_slugs"]
    callable_slugs = contract["services_callable_slugs"]

    response = client.get("/v1/proxy/stats")
    assert response.status_code == 200
    stats = response.json()["data"]

    assert stats["services_registered_slugs"] == registered
    for slug in callable_slugs:
        assert slug in stats["services_registered_slugs"]
    assert "sendgrid" in registered
    assert "sendgrid" not in callable_slugs
    assert "bright-data" not in registered
    assert "bright-data" not in callable_slugs
    assert stats["per_service"] == {}
    assert stats["pools"] == {}
    assert stats["per_service_coverage"] == "unobserved"
    assert stats["pools_coverage"] == "unobserved"
    assert "callable depth is zero" in stats["per_service_honesty"]
    assert "services_callable_slugs" in stats["per_service_honesty"]
    assert "callable depth is zero" in stats["pools_honesty"]
    assert stats["services_registered"] == len(registered)
    assert stats["services_callable"] == len(stats["services_callable_slugs"])
