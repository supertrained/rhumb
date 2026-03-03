"""Output formatting for CLI commands."""

import json
from typing import Any


def render_output(payload: dict[str, Any], as_json: bool = False) -> str:
    """Render command output in human or JSON mode."""
    if as_json:
        return json.dumps(payload, indent=2, sort_keys=True)
    return str(payload)
