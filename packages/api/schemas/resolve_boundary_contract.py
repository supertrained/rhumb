"""Index / Resolve / Runtime boundary contract for Rhumb vNext.

PP-0 intentionally ships this as an executable interface before deeper route-plan
and candidate implementation work.  The contract is deliberately boring and
explicit: every field group has a single owner, downstream layers may reference
upstream facts, and no downstream layer may invent or mutate upstream truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

BoundaryOwner = Literal["index", "resolve", "runtime"]


@dataclass(frozen=True)
class BoundarySection:
    """A product/runtime boundary section with a single accountable owner."""

    owner: BoundaryOwner
    owns: tuple[str, ...]
    must_not: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "owns": list(self.owns),
            "must_not": list(self.must_not),
        }


@dataclass(frozen=True)
class FieldOwnershipGroup:
    """Field ownership row from the vNext field ownership matrix."""

    group: str
    index_stored: tuple[str, ...]
    resolve_computed: tuple[str, ...]
    runtime_issued: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "index_stored": list(self.index_stored),
            "resolve_computed": list(self.resolve_computed),
            "runtime_issued": list(self.runtime_issued),
        }


BOUNDARY_CONTRACT: tuple[BoundarySection, ...] = (
    BoundarySection(
        owner="index",
        owns=(
            "route facts",
            "evidence packets",
            "manifests",
            "stable route IDs",
            "provenance/origin",
            "source risk",
            "review state",
            "freshness",
            "public claim language",
            "AN Score inputs",
        ),
        must_not=(
            "choose caller-specific routes",
            "issue route plans",
            "execute upstream calls",
            "meter executions",
        ),
    ),
    BoundarySection(
        owner="resolve",
        owns=(
            "task/user/org-specific route choice",
            "safety state",
            "stop condition",
            "estimate",
            "route explanation",
            "opaque signed route plan creation",
        ),
        must_not=(
            "fabricate Index facts",
            "mutate score facts",
            "execute upstream calls",
            "rerank after route-plan issuance inside Runtime",
        ),
    ),
    BoundarySection(
        owner="runtime",
        owns=(
            "route-plan enforcement",
            "sandboxing",
            "credential broker use",
            "upstream call",
            "metering",
            "redaction",
            "audit events",
            "receipts",
        ),
        must_not=(
            "score services",
            "discover routes",
            "rank or rerank route candidates",
            "fabricate Resolve decisions",
            "run expired/revoked/mismatched/principal-mismatched route plans",
        ),
    ),
)

FIELD_OWNERSHIP_MATRIX: tuple[FieldOwnershipGroup, ...] = (
    FieldOwnershipGroup(
        group="stable_identity",
        index_stored=(
            "service_id",
            "provider_id",
            "capability_id",
            "route_id",
            "adapter_artifact_id",
        ),
        resolve_computed=("route_candidate_id", "selected_route_id"),
        runtime_issued=("execution_id", "receipt_id"),
    ),
    FieldOwnershipGroup(
        group="evidence",
        index_stored=(
            "manifest_id",
            "manifest_version",
            "manifest_digest",
            "evidence_packet_id",
            "evidence_packet_digest",
            "review_status",
            "promotion_state",
        ),
        resolve_computed=("selected_evidence_references", "evidence_usable_for_request"),
        runtime_issued=("route_plan_evidence_hashes", "receipt_evidence_hashes"),
    ),
    FieldOwnershipGroup(
        group="classification",
        index_stored=(
            "substrate",
            "provenance_origin",
            "source_risk",
            "side_effect_class",
            "data_classes",
        ),
        resolve_computed=("safety_state", "stop_condition", "why_selected", "why_rejected"),
        runtime_issued=("observed_runtime_status", "observed_error", "observed_stop_condition"),
    ),
    FieldOwnershipGroup(
        group="auth_cost_policy",
        index_stored=(
            "supported_credential_modes",
            "required_scopes",
            "route_cost_model",
            "rate_limit_model",
        ),
        resolve_computed=(
            "caller_auth_fit",
            "credential_handle_requirement",
            "cost_estimate",
            "budget_impact",
            "policy_decision",
        ),
        runtime_issued=(
            "credential_handle_used",
            "actual_cost",
            "metering_event",
            "policy_snapshot_hash",
        ),
    ),
    FieldOwnershipGroup(
        group="execution_controls",
        index_stored=(
            "required_sandbox_profile_class",
            "allowlist_references",
            "confirmation_policy_requirement",
        ),
        resolve_computed=(
            "route_plan_expires_at",
            "confirmation_requirement",
            "selected_sandbox_profile_id",
        ),
        runtime_issued=(
            "route_plan_signature",
            "artifact_runtime_hashes",
            "redaction_status",
            "receipt_signature",
            "receipt_status",
        ),
    ),
)

INDEX_STORED_FIELDS = frozenset(
    field for row in FIELD_OWNERSHIP_MATRIX for field in row.index_stored
)
RESOLVE_COMPUTED_FIELDS = frozenset(
    field for row in FIELD_OWNERSHIP_MATRIX for field in row.resolve_computed
)
RUNTIME_ISSUED_FIELDS = frozenset(
    field for row in FIELD_OWNERSHIP_MATRIX for field in row.runtime_issued
)

RUNTIME_FORBIDDEN_DECISION_FIELDS = frozenset(
    {
        "candidate_rank",
        "candidate_score",
        "composite_score",
        "an_score",
        "an_score_override",
        "route_candidates",
        "selected_route_id",
        "why_selected",
        "why_rejected",
    }
)

ROUTE_PLAN_ENFORCEMENT_CHECKS = (
    "signature_valid",
    "not_expired",
    "not_revoked",
    "principal_matches",
    "org_matches",
    "agent_matches",
    "route_id_matches",
    "credential_handle_matches",
    "input_hash_matches",
    "policy_snapshot_current_or_allowed",
    "budget_still_allowed",
    "manifest_digest_matches",
    "evidence_packet_digest_matches",
    "kill_switch_allows_execution",
    "replay_not_seen",
)


def boundary_contract_payload() -> dict[str, Any]:
    """Return the machine-readable PP-0 boundary contract."""

    return {
        "contract_id": "index_resolve_runtime_boundary_v1",
        "source": "PP-0",
        "status": "active",
        "layers": [section.to_dict() for section in BOUNDARY_CONTRACT],
        "field_ownership_matrix": [row.to_dict() for row in FIELD_OWNERSHIP_MATRIX],
        "runtime_forbidden_decision_fields": sorted(RUNTIME_FORBIDDEN_DECISION_FIELDS),
        "route_plan_enforcement_checks": list(ROUTE_PLAN_ENFORCEMENT_CHECKS),
        "invariants": [
            "Index stores route truth; Resolve may reference it but not fabricate or mutate it.",
            "Resolve chooses and explains caller-specific routes; Runtime may enforce but not rerank them.",
            "Runtime executes only a valid Resolve-issued route plan and emits receipts for what it observed.",
            "AN Score inputs remain Index/scoring facts and cannot be inflated because Rhumb owns or generated an adapter.",
        ],
    }


def unexpected_resolve_owned_index_fields(candidate: dict[str, Any]) -> set[str]:
    """Return Index-owned fields a Resolve-only candidate tried to provide as computed fields.

    Resolve responses may echo Index facts under the canonical candidate fields. This guard is for
    implementation seams that label fields as Resolve-computed; those seams must not smuggle
    Index truth into Resolve-owned blobs.
    """

    resolve_blob = candidate.get("resolve_computed")
    if not isinstance(resolve_blob, dict):
        return set()
    return INDEX_STORED_FIELDS.intersection(resolve_blob.keys())


def runtime_decision_mutations(runtime_payload: dict[str, Any]) -> set[str]:
    """Return decision/ranking fields Runtime attempted to issue or mutate."""

    mutated = set(runtime_payload.keys()).intersection(RUNTIME_FORBIDDEN_DECISION_FIELDS)
    runtime_issued = runtime_payload.get("runtime_issued")
    if isinstance(runtime_issued, dict):
        mutated.update(set(runtime_issued.keys()).intersection(RUNTIME_FORBIDDEN_DECISION_FIELDS))
    return mutated


def missing_route_plan_enforcement_checks(checks: dict[str, bool]) -> set[str]:
    """Return required route-plan checks that are missing or false."""

    return set(name for name in ROUTE_PLAN_ENFORCEMENT_CHECKS if checks.get(name) is not True)
