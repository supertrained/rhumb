"""Smoke tests for scaffolded API routes."""

from fastapi.testclient import TestClient

ROUTES = [
    "/healthz",
    "/v1/services",
    "/v1/services/stripe",
    "/v1/services/stripe/score",
    "/v1/services/stripe/failures",
    "/v1/services/stripe/history",
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
    """POST skeletons should respond without server errors."""
    assert client.post("/v1/evaluate").status_code == 200
    assert client.post("/v1/services/stripe/report").status_code == 200
