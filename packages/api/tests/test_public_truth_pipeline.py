"""Guard the public-truth counts parser against nested endpoint key collisions."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_generator():
    path = Path(__file__).resolve().parents[3] / "scripts" / "generate_agent_capabilities.py"
    spec = importlib.util.spec_from_file_location("generate_agent_capabilities", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_public_truth_counts_uses_top_level_numbers_not_endpoint_paths():
    module = _load_generator()
    counts = module.load_public_truth_counts()

    assert isinstance(counts["services"], int)
    assert counts["services"] > 0
    assert isinstance(counts["capabilities"], int)
    assert counts["capabilities"] > 0
    assert counts["categories"] == 87
    assert counts["capabilityDomains"] == 149
    assert counts["callableProviders"] == 28
    assert counts["registeredProviders"] == 29
    assert "services?limit" not in str(counts["services"])
