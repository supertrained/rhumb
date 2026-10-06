"""CLI configuration helpers."""

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class CLIConfig:
    """Runtime config for API communication."""

    api_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "RHUMB_API_BASE_URL",
            "https://api.rhumb.dev/v1",
        )
    )
