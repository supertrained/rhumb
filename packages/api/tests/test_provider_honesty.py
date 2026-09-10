from __future__ import annotations

from services.provider_honesty import rail_honesty_fields, stamp_rail_honesty


def test_index_engine_schema_ready_is_not_tenant_callable() -> None:
    fields = rail_honesty_fields(
        endpoint_pattern="POST /{index}/_search",
        configured=False,
        available_for_execute=True,
    )
    assert fields == {
        "schema_ready": True,
        "tenant_configured": False,
        "callable": False,
    }


def test_configured_healthy_rail_is_callable() -> None:
    fields = rail_honesty_fields(
        endpoint_pattern="POST /search",
        configured=True,
        available_for_execute=True,
    )
    assert fields == {
        "schema_ready": True,
        "tenant_configured": True,
        "callable": True,
    }


def test_open_breaker_is_not_callable() -> None:
    fields = rail_honesty_fields(
        endpoint_pattern="POST /search",
        configured=True,
        available_for_execute=False,
    )
    assert fields == {
        "schema_ready": True,
        "tenant_configured": True,
        "callable": False,
    }


def test_missing_endpoint_is_not_schema_ready() -> None:
    fields = rail_honesty_fields(
        endpoint_pattern="  ",
        configured=True,
        available_for_execute=True,
    )
    assert fields == {
        "schema_ready": False,
        "tenant_configured": True,
        "callable": False,
    }


def test_stamp_overwrites_honesty_after_configured_flips() -> None:
    provider = {
        "endpoint_pattern": "POST /{index}/_search",
        "configured": False,
        "available_for_execute": True,
        "schema_ready": True,
        "tenant_configured": True,
        "callable": True,
    }
    stamped = stamp_rail_honesty(provider)
    assert stamped["tenant_configured"] is False
    assert stamped["callable"] is False
    assert stamped["schema_ready"] is True
