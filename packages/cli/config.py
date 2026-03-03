"""CLI configuration helpers."""

from dataclasses import dataclass


@dataclass(slots=True)
class CLIConfig:
    """Runtime config for API communication."""

    api_base_url: str = "http://localhost:8000/v1"
