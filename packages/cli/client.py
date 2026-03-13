"""HTTP client wrapper for Rhumb API."""

from typing import Any

import httpx

from config import CLIConfig


class RhumbAPIClient:
    """Lightweight synchronous API client for CLI commands."""

    DEFAULT_HEADERS = {
        "User-Agent": "rhumb-cli/0.0.1",
        "X-Rhumb-Client": "cli",
        "X-Agent-Name": "rhumb-cli",
    }

    def __init__(self, config: CLIConfig | None = None) -> None:
        self.config = config or CLIConfig()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a GET request and return parsed JSON."""
        response = httpx.get(
            f"{self.config.api_base_url}{path}",
            params=params,
            headers=self.DEFAULT_HEADERS,
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())

    def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        """Perform a POST request and return parsed JSON."""
        response = httpx.post(
            f"{self.config.api_base_url}{path}",
            json=json,
            headers=self.DEFAULT_HEADERS,
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())
