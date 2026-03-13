"""Provisioning flow schema and Supabase-backed state store.

Defines the flow types (signup, oauth, payment, tos, confirmation),
the state machine (pending → in_progress → human_action_needed → complete/failed/expired),
and a ``ProvisioningFlowStore`` that persists flow records in Supabase.

In tests the store operates against a mock Supabase client (in-memory dict).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------


class FlowType(str, Enum):
    """Types of provisioning flows."""

    SIGNUP = "signup"
    OAUTH = "oauth"
    PAYMENT = "payment"
    TOS = "tos"
    CONFIRMATION = "confirmation"


class FlowState(str, Enum):
    """Provisioning flow state machine.

    Valid transitions::

        pending → in_progress → human_action_needed → complete
                                                    → failed
                                                    → expired
        pending → failed  (immediate failure, e.g. unsupported service)
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    HUMAN_ACTION_NEEDED = "human_action_needed"
    COMPLETE = "complete"
    FAILED = "failed"
    EXPIRED = "expired"


# Legal state transitions (from → set of allowed targets).
VALID_TRANSITIONS: Dict[FlowState, set[FlowState]] = {
    FlowState.PENDING: {FlowState.IN_PROGRESS, FlowState.FAILED},
    FlowState.IN_PROGRESS: {
        FlowState.HUMAN_ACTION_NEEDED,
        FlowState.COMPLETE,
        FlowState.FAILED,
    },
    FlowState.HUMAN_ACTION_NEEDED: {
        FlowState.COMPLETE,
        FlowState.FAILED,
        FlowState.EXPIRED,
        FlowState.IN_PROGRESS,  # retry
    },
    FlowState.COMPLETE: set(),  # terminal
    FlowState.FAILED: set(),  # terminal
    FlowState.EXPIRED: set(),  # terminal
}


# ------------------------------------------------------------------
# Data model
# ------------------------------------------------------------------


@dataclass
class ProvisioningFlowSchema:
    """Provisioning flow record (mirrors the ``provisioning_flows`` table)."""

    flow_id: str
    agent_id: str
    service: str
    flow_type: str  # FlowType value stored as string
    state: str  # FlowState value stored as string

    payload: Dict[str, Any] = field(default_factory=dict)
    callback_data: Optional[Dict[str, Any]] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None
    human_action_url: Optional[str] = None
    error_message: Optional[str] = None
    retries: int = 0
    max_retries: int = 3


# ------------------------------------------------------------------
# Store
# ------------------------------------------------------------------


class ProvisioningFlowStore:
    """Manage provisioning flow state in Supabase (or in-memory for tests)."""

    def __init__(self, supabase_client: Any = None) -> None:
        self.supabase = supabase_client
        # In-memory fallback for tests
        self._mem: Dict[str, Dict[str, Any]] = {}
        # Orchestration sequences stored per (agent_id, service)
        self._sequences: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_flow(
        self,
        agent_id: str,
        service: str,
        flow_type: FlowType,
        payload: Dict[str, Any],
        *,
        ttl_hours: int = 24,
    ) -> str:
        """Create a new provisioning flow.

        Returns:
            The generated ``flow_id`` (UUID string).
        """
        flow_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=ttl_hours)

        record: Dict[str, Any] = {
            "flow_id": flow_id,
            "agent_id": agent_id,
            "service": service,
            "flow_type": flow_type.value,
            "state": FlowState.PENDING.value,
            "payload": json.dumps(payload) if isinstance(payload, dict) else payload,
            "callback_data": None,
            "human_action_url": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "retries": 0,
        }

        if self.supabase is not None:
            await self.supabase.table("provisioning_flows").insert(record).execute()
        else:
            self._mem[flow_id] = record

        return flow_id

    async def get_flow(self, flow_id: str) -> Optional[ProvisioningFlowSchema]:
        """Retrieve a flow by its ID."""
        data: Optional[Dict[str, Any]] = None

        if self.supabase is not None:
            response = await (
                self.supabase.table("provisioning_flows")
                .select("*")
                .eq("flow_id", flow_id)
                .single()
                .execute()
            )
            data = response.data if response.data else None
        else:
            data = self._mem.get(flow_id)

        if data is None:
            return None

        # Deserialise JSON fields
        payload = data.get("payload", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)

        callback_data = data.get("callback_data")
        if isinstance(callback_data, str):
            callback_data = json.loads(callback_data)

        return ProvisioningFlowSchema(
            flow_id=data["flow_id"],
            agent_id=data["agent_id"],
            service=data["service"],
            flow_type=data["flow_type"],
            state=data["state"],
            payload=payload,
            callback_data=callback_data,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            expires_at=data.get("expires_at"),
            human_action_url=data.get("human_action_url"),
            error_message=data.get("error_message"),
            retries=data.get("retries", 0),
        )

    async def update_flow_state(
        self,
        flow_id: str,
        new_state: FlowState,
        *,
        callback_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Transition a flow to *new_state*.

        Raises:
            ValueError: If the transition is not valid.
        """
        flow = await self.get_flow(flow_id)
        if flow is None:
            raise ValueError(f"Flow {flow_id} not found")

        current = FlowState(flow.state)
        allowed = VALID_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition {current.value} → {new_state.value} "
                f"(allowed: {[s.value for s in allowed]})"
            )

        update: Dict[str, Any] = {
            "state": new_state.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if callback_data is not None:
            update["callback_data"] = json.dumps(callback_data)
        if error_message is not None:
            update["error_message"] = error_message

        if self.supabase is not None:
            await self.supabase.table("provisioning_flows").update(update).eq(
                "flow_id", flow_id
            ).execute()
        else:
            self._mem[flow_id].update(update)

    async def set_human_action_url(self, flow_id: str, url: str) -> None:
        """Set the URL for the human to visit and transition to HUMAN_ACTION_NEEDED."""
        flow = await self.get_flow(flow_id)
        if flow is None:
            raise ValueError(f"Flow {flow_id} not found")

        # Transition to IN_PROGRESS first if PENDING
        current = FlowState(flow.state)
        if current == FlowState.PENDING:
            await self.update_flow_state(flow_id, FlowState.IN_PROGRESS)

        update: Dict[str, Any] = {
            "human_action_url": url,
            "state": FlowState.HUMAN_ACTION_NEEDED.value,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if self.supabase is not None:
            await self.supabase.table("provisioning_flows").update(update).eq(
                "flow_id", flow_id
            ).execute()
        else:
            self._mem[flow_id].update(update)

    async def increment_retries(self, flow_id: str) -> int:
        """Increment retry counter and return the new value."""
        flow = await self.get_flow(flow_id)
        if flow is None:
            raise ValueError(f"Flow {flow_id} not found")

        new_retries = flow.retries + 1

        if self.supabase is not None:
            await self.supabase.table("provisioning_flows").update(
                {"retries": new_retries, "updated_at": datetime.utcnow().isoformat()}
            ).eq("flow_id", flow_id).execute()
        else:
            self._mem[flow_id]["retries"] = new_retries

        return new_retries

    async def check_expiration(self, flow_id: str) -> bool:
        """Check if a flow has expired and mark it if so.

        Returns:
            ``True`` if the flow is (now) expired.
        """
        flow = await self.get_flow(flow_id)
        if flow is None:
            return False

        if flow.state in (FlowState.COMPLETE.value, FlowState.FAILED.value, FlowState.EXPIRED.value):
            return flow.state == FlowState.EXPIRED.value

        if flow.expires_at is not None:
            expires = datetime.fromisoformat(flow.expires_at)
            if datetime.utcnow() > expires:
                # Force-set to expired (bypass normal transition validation)
                update: Dict[str, Any] = {
                    "state": FlowState.EXPIRED.value,
                    "updated_at": datetime.utcnow().isoformat(),
                    "error_message": "Flow expired",
                }
                if self.supabase is not None:
                    await self.supabase.table("provisioning_flows").update(update).eq(
                        "flow_id", flow_id
                    ).execute()
                else:
                    self._mem[flow_id].update(update)
                return True

        return False

    # ------------------------------------------------------------------
    # Orchestration sequence tracking
    # ------------------------------------------------------------------

    async def set_provisioning_sequence(
        self,
        agent_id: str,
        service: str,
        sequence: List[FlowType],
        current_index: int,
    ) -> None:
        """Store the provisioning sequence for an agent+service pair."""
        key = f"{agent_id}:{service}"
        self._sequences[key] = {
            "sequence": [ft.value for ft in sequence],
            "current_index": current_index,
        }

    async def get_provisioning_sequence(
        self, agent_id: str, service: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the provisioning sequence for an agent+service pair."""
        key = f"{agent_id}:{service}"
        data = self._sequences.get(key)
        if data is None:
            return None
        return {
            "sequence": [FlowType(v) for v in data["sequence"]],
            "current_index": data["current_index"],
        }

    async def list_flows_by_agent(
        self, agent_id: str, *, state: Optional[FlowState] = None
    ) -> List[ProvisioningFlowSchema]:
        """List all flows for an agent, optionally filtered by state."""
        results: List[ProvisioningFlowSchema] = []

        if self.supabase is not None:
            query = (
                self.supabase.table("provisioning_flows")
                .select("*")
                .eq("agent_id", agent_id)
            )
            if state is not None:
                query = query.eq("state", state.value)
            response = await query.execute()
            for row in response.data or []:
                flow = await self.get_flow(row["flow_id"])
                if flow:
                    results.append(flow)
        else:
            for record in self._mem.values():
                if record["agent_id"] != agent_id:
                    continue
                if state is not None and record["state"] != state.value:
                    continue
                flow = await self.get_flow(record["flow_id"])
                if flow:
                    results.append(flow)

        return results


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_flow_store: Optional[ProvisioningFlowStore] = None


def get_flow_store(supabase_client: Any = None) -> ProvisioningFlowStore:
    """Return (or create) the global :class:`ProvisioningFlowStore` singleton."""
    global _flow_store
    if _flow_store is None:
        _flow_store = ProvisioningFlowStore(supabase_client)
    return _flow_store
