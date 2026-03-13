"""Smoke tests for scaffolded API routes."""

from fastapi.testclient import TestClient

ROUTES = [
    "/healthz",
    "/v1/services",
    "/v1/services/stripe",
    "/v1/services/stripe/score",
    "/v1/services/stripe/reviews",
    "/v1/services/stripe/evidence",
    "/v1/services/stripe/failures",
    "/v1/services/stripe/history",
    "/v1/reviews/stats",
    "/v1/search?q=payments",
    "/v1/leaderboard/payments",
    "/v1/compare?services=stripe,resend",
    "/v1/alerts",
]


def test_routes_return_success(client: TestClient) -> None:
    """Every scaffold route should return HTTP 200."""
    for route in ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route


def test_post_routes_accept_requests(client: TestClient) -> None:
    """POST routes should respond without server errors."""
    score_payload = {
        "service_slug": "stripe",
        "dimensions": {
            "I1": 9.5,
            "I2": 9.0,
            "I3": 8.5,
            "I4": 9.5,
            "I5": 9.0,
            "I6": 8.0,
            "I7": 9.0,
            "F1": 9.0,
            "F2": 9.5,
            "F3": 9.5,
            "F4": 8.5,
            "F5": 10.0,
            "F6": 9.0,
            "F7": 9.0,
            "O1": 9.0,
            "O2": 9.0,
            "O3": 8.0,
        },
        "evidence_count": 72,
        "freshness": "12 minutes ago",
        "probe_types": ["health", "auth", "schema", "load", "idempotency"],
        "production_telemetry": True,
    }

    assert client.post("/v1/score", json=score_payload).status_code == 200
    assert client.post("/v1/evaluate").status_code == 200
    assert client.post("/v1/services/stripe/report").status_code == 200
    assert client.post("/v1/probes/run", json={"service_slug": "stripe"}).status_code == 200
    assert client.post("/v1/probes/schedule/run", json={"dry_run": True}).status_code == 200
