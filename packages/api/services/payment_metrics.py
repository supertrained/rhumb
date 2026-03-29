"""
Payment system structured logging and metrics.

Emits structured payment logs that Railway can surface in plain-text log views.
All payment events go through here for consistent observability.
"""

import json
import logging
import time
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("rhumb.payments")


def log_payment_event(
    event: str,
    *,
    org_id: Optional[str] = None,
    amount_usd_cents: Optional[int] = None,
    execution_id: Optional[str] = None,
    provider: Optional[str] = None,
    capability_id: Optional[str] = None,
    tx_hash: Optional[str] = None,
    network: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
    **extra,
):
    """Emit a structured payment event log."""
    data = {
        "event": event,
        "org_id": org_id,
        "amount_usd_cents": amount_usd_cents,
        "execution_id": execution_id,
        "provider": provider,
        "capability_id": capability_id,
        "success": success,
    }
    if tx_hash:
        data["tx_hash"] = tx_hash
    if network:
        data["network"] = network
    if error:
        data["error"] = error
    data.update(extra)

    # Filter None values
    data = {k: v for k, v in data.items() if v is not None}
    payload = json.dumps(data, sort_keys=True, default=str)

    if success:
        logger.info("payment.%s %s", event, payload, extra={"payment": data})
    else:
        logger.warning("payment.%s %s", event, payload, extra={"payment": data})


@contextmanager
def payment_timer(event: str, **kwargs):
    """Context manager that logs a payment event with duration_ms."""
    start = time.monotonic()
    try:
        yield
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        log_payment_event(event, duration_ms=duration_ms, **kwargs)
    except Exception as e:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        log_payment_event(
            event, success=False, error=str(e), duration_ms=duration_ms, **kwargs
        )
        raise
