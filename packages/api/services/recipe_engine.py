"""Recipe execution engine — DAG-based, step-level budgets (WU-42.1).

Layer 3 core: validates recipe definitions, validates DAGs for acyclicity,
executes steps in dependency order with per-step budget enforcement,
parameter mapping between steps, and partial-failure handling.

Architectural rules (from Resolve spec):
  - Recipes are COMPILED, not generated. No LLM in the execution path.
  - DAG must be acyclic (enforced at compile/validation time).
  - Max fan-out per step, max nesting depth (3), max steps (100).
  - Per-step budget enforcement is mandatory.
  - Content firewall at every step transition (deferred to WU-42.2).
  - Every step produces an immutable execution receipt.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ── Safety limits ─────────────────────────────────────────────────────

MAX_STEPS_PER_RECIPE = 100
MAX_NESTING_DEPTH = 3
MAX_FAN_OUT = 50  # Max parallel steps from a single parent
MAX_TOTAL_COST_USD_DEFAULT = 10.0
MAX_STEP_TIMEOUT_MS_DEFAULT = 60_000
MAX_RECIPE_TIMEOUT_MS_DEFAULT = 300_000


# ── Enums ─────────────────────────────────────────────────────────────


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMED_OUT = "timed_out"


class RecipeStatus(str, Enum):
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"  # Some steps succeeded, some failed
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMED_OUT = "timed_out"  # AUD-6: total recipe timeout exceeded


# AUD-6: Financial operation categories for restoration logic
class OperationType(str, Enum):
    """Classifies step operations for restoration/rollback decisions."""
    READ = "read"              # Safe reads — no rollback needed
    WRITE = "write"            # Non-financial mutations
    FINANCIAL = "financial"    # Charges, transfers, refunds — require special handling
    UNKNOWN = "unknown"        # Unclassified

# Capability IDs that are inherently financial
_FINANCIAL_CAPABILITIES = frozenset([
    "payment.charge", "payment.create", "payment.capture",
    "payment.refund", "billing.create_invoice", "billing.charge",
    "transfer.send", "transfer.create",
    "wallet.topup", "wallet.withdraw",
    "subscription.create", "subscription.cancel",
])


class FailureMode(str, Enum):
    HALT = "halt"
    CONTINUE = "continue"


# ── Data types ────────────────────────────────────────────────────────


@dataclass(slots=True)
class StepDefinition:
    """A step in a recipe definition."""

    step_id: str
    capability_id: str
    capability_version: str = "^1.0.0"
    depends_on: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    outputs_captured: dict[str, str] = field(default_factory=dict)
    failure_mode: FailureMode = FailureMode.HALT
    retries: int = 0
    retry_backoff: str = "exponential"
    retry_base_ms: int = 1000
    max_cost_usd: float = 1.0
    timeout_ms: int = MAX_STEP_TIMEOUT_MS_DEFAULT
    # AUD-6: operation type for restoration logic
    operation_type: str = "unknown"  # read | write | financial | unknown


@dataclass(slots=True)
class RecipeDefinition:
    """Validated, compiled recipe definition."""

    recipe_id: str
    name: str
    version: str
    category: str = ""
    stability: str = "beta"
    tier: str = "premium"
    inputs_schema: dict[str, Any] = field(default_factory=dict)
    outputs_schema: dict[str, Any] = field(default_factory=dict)
    steps: list[StepDefinition] = field(default_factory=list)
    dag_edges: list[tuple[str, str]] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    max_total_cost_usd: float = MAX_TOTAL_COST_USD_DEFAULT
    per_step_budgets_enforced: bool = True
    on_budget_exceeded: str = "halt_current_step"
    total_timeout_ms: int = MAX_RECIPE_TIMEOUT_MS_DEFAULT
    idempotency_supported: bool = True
    idempotency_window_seconds: int = 3600


@dataclass(slots=True)
class StepResult:
    """Execution result for a single step."""

    step_id: str
    status: StepStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    duration_ms: int = 0
    receipt_id: str = ""
    error: str | None = None
    retries_used: int = 0
    provider_used: str | None = None
    # AUD-6: financial operation tracking
    is_financial: bool = False
    operation_type: str = "unknown"


@dataclass(slots=True)
class RecipeExecution:
    """Full recipe execution state."""

    execution_id: str
    recipe_id: str
    status: RecipeStatus
    step_results: dict[str, StepResult] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error: str | None = None
    receipt_chain_hash: str = ""
    # AUD-6: financial operation summary
    financial_step_count: int = 0
    financial_steps_succeeded: int = 0
    has_financial_operations: bool = False


# ── DAG Validator ─────────────────────────────────────────────────────


class DAGValidationError(Exception):
    """Raised when a recipe DAG fails validation."""

    pass


class DAGValidator:
    """Validates recipe DAGs for structural correctness."""

    @staticmethod
    def validate(recipe: RecipeDefinition) -> list[str]:
        """Validate a recipe's DAG. Returns topological order.

        Raises DAGValidationError on:
          - Cycles
          - Missing step references
          - Fan-out exceeding MAX_FAN_OUT
          - Too many steps
        """
        steps_by_id = {step.step_id: step for step in recipe.steps}
        step_ids = set(steps_by_id.keys())

        # ── Step count limit ──
        if len(recipe.steps) > MAX_STEPS_PER_RECIPE:
            raise DAGValidationError(
                f"Recipe has {len(recipe.steps)} steps, exceeds maximum of {MAX_STEPS_PER_RECIPE}"
            )

        if not recipe.steps:
            raise DAGValidationError("Recipe has no steps")

        # ── Duplicate step IDs ──
        if len(step_ids) != len(recipe.steps):
            raise DAGValidationError("Duplicate step_id found in recipe")

        # ── Reference validation ──
        for step in recipe.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise DAGValidationError(
                        f"Step '{step.step_id}' depends on unknown step '{dep}'"
                    )

        # ── Build adjacency for topo sort + cycle detection ──
        graph: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {sid: 0 for sid in step_ids}

        for step in recipe.steps:
            for dep in step.depends_on:
                graph[dep].append(step.step_id)
                in_degree[step.step_id] += 1

        # ── Fan-out check ──
        for node, successors in graph.items():
            if len(successors) > MAX_FAN_OUT:
                raise DAGValidationError(
                    f"Step '{node}' has fan-out of {len(successors)}, exceeds maximum of {MAX_FAN_OUT}"
                )

        # ── Kahn's algorithm for topological sort + cycle detection ──
        queue: deque[str] = deque()
        for sid, degree in in_degree.items():
            if degree == 0:
                queue.append(sid)

        topo_order: list[str] = []
        while queue:
            node = queue.popleft()
            topo_order.append(node)
            for successor in graph[node]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(topo_order) != len(step_ids):
            remaining = step_ids - set(topo_order)
            raise DAGValidationError(
                f"Cycle detected in recipe DAG involving steps: {remaining}"
            )

        # ── Validate DAG edges match step dependencies ──
        for edge_from, edge_to in recipe.dag_edges:
            if edge_from not in step_ids:
                raise DAGValidationError(
                    f"DAG edge references unknown step '{edge_from}'"
                )
            if edge_to not in step_ids:
                raise DAGValidationError(
                    f"DAG edge references unknown step '{edge_to}'"
                )

        return topo_order


# ── Parameter Resolver ────────────────────────────────────────────────


class ParameterResolver:
    """Resolves $ref parameter bindings between recipe inputs and step outputs."""

    @staticmethod
    def resolve(
        parameters: dict[str, Any],
        recipe_inputs: dict[str, Any],
        step_outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve $ref parameters to concrete values.

        Supported refs:
          - inputs.field_name → recipe_inputs[field_name]
          - steps.step_id.outputs.field_name → step_outputs[step_id][field_name]
        """
        resolved: dict[str, Any] = {}
        for key, value in parameters.items():
            resolved[key] = ParameterResolver._resolve_value(
                value, recipe_inputs, step_outputs
            )
        return resolved

    @staticmethod
    def _resolve_value(
        value: Any,
        recipe_inputs: dict[str, Any],
        step_outputs: dict[str, dict[str, Any]],
    ) -> Any:
        if not isinstance(value, dict):
            return value

        ref = value.get("$ref")
        if ref is None:
            # Recurse into nested dicts
            return {
                k: ParameterResolver._resolve_value(v, recipe_inputs, step_outputs)
                for k, v in value.items()
            }

        return ParameterResolver._resolve_ref(ref, recipe_inputs, step_outputs)

    @staticmethod
    def _resolve_ref(
        ref: str,
        recipe_inputs: dict[str, Any],
        step_outputs: dict[str, dict[str, Any]],
    ) -> Any:
        parts = ref.split(".")

        # inputs.field_name
        if parts[0] == "inputs" and len(parts) >= 2:
            field_name = ".".join(parts[1:])
            return recipe_inputs.get(field_name)

        # steps.step_id.outputs.field_name
        if parts[0] == "steps" and len(parts) >= 4 and parts[2] == "outputs":
            step_id = parts[1]
            field_name = ".".join(parts[3:])
            outputs = step_outputs.get(step_id, {})
            return outputs.get(field_name)

        raise ValueError(f"Unresolvable $ref: {ref}")


# ── Budget Tracker ────────────────────────────────────────────────────


@dataclass
class BudgetTracker:
    """Tracks per-step and total budget during recipe execution."""

    max_total_usd: float
    per_step_enforced: bool
    on_exceeded: str  # "halt_current_step" | "halt_recipe"
    spent_usd: float = 0.0

    def check_step_budget(self, step: StepDefinition, estimated_cost: float) -> bool:
        """Return True if the step can proceed within budget."""
        if self.per_step_enforced and estimated_cost > step.max_cost_usd:
            return False
        if self.spent_usd + estimated_cost > self.max_total_usd:
            return False
        return True

    def record_spend(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.max_total_usd - self.spent_usd)


# ── Step Executor (interface) ─────────────────────────────────────────


class StepExecutor:
    """Executes a single recipe step by calling the capability execution layer.

    This is the integration point with the existing L2 execution path.
    In tests, this is replaced with a mock/stub.
    """

    async def execute_step(
        self,
        step: StepDefinition,
        resolved_params: dict[str, Any],
        credential_mode: str = "rhumb_managed",
    ) -> StepResult:
        """Execute a single capability via Layer 2.

        Override this in production to call the real execution path.
        """
        # Default implementation — returns a stub result
        # Production override will call the L2 execute route
        return StepResult(
            step_id=step.step_id,
            status=StepStatus.SUCCEEDED,
            outputs={},
            cost_usd=0.0,
            duration_ms=0,
            receipt_id=f"rcpt_{uuid.uuid4().hex[:24]}",
        )


# ── Recipe Engine ─────────────────────────────────────────────────────


class RecipeEngine:
    """Executes validated recipes according to their DAG.

    Core flow:
    1. Validate DAG → topological order
    2. For each step in order:
       a. Check budget
       b. Resolve parameters ($ref bindings)
       c. Execute step via StepExecutor
       d. Capture outputs
       e. Handle failure (halt or continue)
    3. Compute final status and total cost
    """

    def __init__(self, step_executor: StepExecutor | None = None) -> None:
        self._executor = step_executor or StepExecutor()
        self._validator = DAGValidator()

    async def execute(
        self,
        recipe: RecipeDefinition,
        inputs: dict[str, Any],
        credential_mode: str = "rhumb_managed",
    ) -> RecipeExecution:
        """Execute a recipe end-to-end.

        Returns a RecipeExecution with per-step results, total cost,
        and final status.
        """
        execution_id = f"rexec_{uuid.uuid4().hex[:24]}"
        execution = RecipeExecution(
            execution_id=execution_id,
            recipe_id=recipe.recipe_id,
            status=RecipeStatus.VALIDATING,
        )

        # ── Step 1: Validate DAG ──
        try:
            topo_order = self._validator.validate(recipe)
        except DAGValidationError as e:
            execution.status = RecipeStatus.FAILED
            execution.error = f"DAG validation failed: {e}"
            execution.completed_at = datetime.now(timezone.utc)
            return execution

        # ── Step 2: Initialize budget tracker ──
        budget = BudgetTracker(
            max_total_usd=recipe.max_total_cost_usd,
            per_step_enforced=recipe.per_step_budgets_enforced,
            on_exceeded=recipe.on_budget_exceeded,
        )

        # ── Step 3: Execute steps in topological order ──
        execution.status = RecipeStatus.RUNNING
        steps_by_id = {step.step_id: step for step in recipe.steps}
        step_outputs: dict[str, dict[str, Any]] = {}
        halted = False
        any_failed = False
        any_succeeded = False

        start_time = time.monotonic()

        for step_id in topo_order:
            step = steps_by_id[step_id]

            # AUD-6: enforce total recipe timeout
            elapsed_ms = (time.monotonic() - start_time) * 1000
            if elapsed_ms > recipe.total_timeout_ms:
                execution.step_results[step_id] = StepResult(
                    step_id=step_id,
                    status=StepStatus.TIMED_OUT,
                    error=(
                        f"Recipe total timeout exceeded: "
                        f"{elapsed_ms:.0f}ms > {recipe.total_timeout_ms}ms"
                    ),
                )
                # Mark remaining steps as timed out
                remaining_idx = topo_order.index(step_id)
                for remaining_id in topo_order[remaining_idx + 1:]:
                    execution.step_results[remaining_id] = StepResult(
                        step_id=remaining_id,
                        status=StepStatus.TIMED_OUT,
                        error="Skipped: recipe total timeout exceeded",
                    )
                execution.status = RecipeStatus.TIMED_OUT
                break

            # Skip if a prior halt-mode failure stopped the pipeline
            if halted:
                execution.step_results[step_id] = StepResult(
                    step_id=step_id,
                    status=StepStatus.SKIPPED,
                    error="Skipped due to prior step failure (halt mode)",
                )
                continue

            # Check if dependencies succeeded
            deps_ok = True
            for dep in step.depends_on:
                dep_result = execution.step_results.get(dep)
                if dep_result is None or dep_result.status not in (
                    StepStatus.SUCCEEDED,
                ):
                    deps_ok = False
                    break

            if not deps_ok:
                execution.step_results[step_id] = StepResult(
                    step_id=step_id,
                    status=StepStatus.SKIPPED,
                    error="Skipped: dependency did not succeed",
                )
                continue

            # Budget check (estimate = step's max_cost_usd as upper bound)
            if not budget.check_step_budget(step, step.max_cost_usd):
                execution.step_results[step_id] = StepResult(
                    step_id=step_id,
                    status=StepStatus.BUDGET_EXCEEDED,
                    error=(
                        f"Budget exceeded: step max ${step.max_cost_usd:.4f}, "
                        f"recipe remaining ${budget.remaining_usd:.4f}"
                    ),
                )
                any_failed = True
                if step.failure_mode == FailureMode.HALT:
                    halted = True
                    execution.status = RecipeStatus.BUDGET_EXCEEDED
                continue

            # Resolve parameters
            try:
                resolved_params = ParameterResolver.resolve(
                    step.parameters, inputs, step_outputs
                )
            except (ValueError, KeyError) as e:
                execution.step_results[step_id] = StepResult(
                    step_id=step_id,
                    status=StepStatus.FAILED,
                    error=f"Parameter resolution failed: {e}",
                )
                any_failed = True
                if step.failure_mode == FailureMode.HALT:
                    halted = True
                continue

            # Execute with retries
            result = await self._execute_with_retries(
                step, resolved_params, credential_mode
            )

            # Record result
            execution.step_results[step_id] = result
            budget.record_spend(result.cost_usd)
            execution.total_cost_usd += result.cost_usd

            # AUD-6: tag financial operations
            if step.operation_type == "financial":
                result.is_financial = True
                result.operation_type = "financial"
                execution.financial_step_count += 1
                execution.has_financial_operations = True
            else:
                result.operation_type = step.operation_type

            if result.status == StepStatus.SUCCEEDED:
                any_succeeded = True
                # Capture outputs for downstream $ref resolution
                step_outputs[step_id] = result.outputs
                if step.operation_type == "financial":
                    execution.financial_steps_succeeded += 1
            else:
                any_failed = True
                if step.failure_mode == FailureMode.HALT:
                    halted = True

        # ── Step 4: Compute final status ──
        end_time = time.monotonic()
        execution.total_duration_ms = int((end_time - start_time) * 1000)
        execution.completed_at = datetime.now(timezone.utc)

        if execution.status in (RecipeStatus.BUDGET_EXCEEDED, RecipeStatus.TIMED_OUT):
            pass  # Already set by the enforcement code
        elif not any_failed:
            execution.status = RecipeStatus.COMPLETED
        elif any_succeeded and any_failed:
            execution.status = RecipeStatus.PARTIAL
        else:
            execution.status = RecipeStatus.FAILED

        return execution

    async def _execute_with_retries(
        self,
        step: StepDefinition,
        resolved_params: dict[str, Any],
        credential_mode: str,
    ) -> StepResult:
        """Execute a step with retry policy."""
        last_result: StepResult | None = None

        for attempt in range(1 + step.retries):
            result = await self._executor.execute_step(
                step, resolved_params, credential_mode
            )
            result.retries_used = attempt

            if result.status == StepStatus.SUCCEEDED:
                return result

            last_result = result

            # Don't retry on budget exceeded or timeout
            if result.status in (StepStatus.BUDGET_EXCEEDED, StepStatus.TIMED_OUT):
                return result

        return last_result or StepResult(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="All retries exhausted",
        )


# ── Recipe compiler (from raw JSON → validated RecipeDefinition) ──────


def compile_recipe(raw: dict[str, Any]) -> RecipeDefinition:
    """Parse and validate a raw recipe JSON into a RecipeDefinition.

    Raises ValueError on invalid schema.
    """
    if not isinstance(raw, dict):
        raise ValueError("Recipe must be a JSON object")

    recipe_id = raw.get("recipe_id")
    if not recipe_id or not isinstance(recipe_id, str):
        raise ValueError("recipe_id is required and must be a string")

    name = raw.get("name", recipe_id)
    version = raw.get("version", "1.0.0")

    # Parse steps
    raw_steps = raw.get("steps", [])
    if not isinstance(raw_steps, list):
        raise ValueError("steps must be an array")

    steps: list[StepDefinition] = []
    for i, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Step {i} must be an object")

        step_id = raw_step.get("step_id")
        if not step_id:
            raise ValueError(f"Step {i} missing step_id")

        capability_id = raw_step.get("capability_id")
        if not capability_id:
            raise ValueError(f"Step '{step_id}' missing capability_id")

        failure_config = raw_step.get("failure_mode", {})
        if isinstance(failure_config, dict):
            on_failure = failure_config.get("on_failure", "halt")
            retries = failure_config.get("retries", 0)
            retry_backoff = failure_config.get("retry_backoff", "exponential")
            retry_base_ms = failure_config.get("retry_base_ms", 1000)
        else:
            on_failure = "halt"
            retries = 0
            retry_backoff = "exponential"
            retry_base_ms = 1000

        budget_config = raw_step.get("budget", {})
        max_cost = budget_config.get("max_cost_usd", 1.0) if isinstance(budget_config, dict) else 1.0
        timeout = budget_config.get("timeout_ms", MAX_STEP_TIMEOUT_MS_DEFAULT) if isinstance(budget_config, dict) else MAX_STEP_TIMEOUT_MS_DEFAULT

        # AUD-6: classify operation type from capability_id
        explicit_op_type = raw_step.get("operation_type", None)
        if explicit_op_type and explicit_op_type in ("read", "write", "financial"):
            op_type = explicit_op_type
        elif capability_id in _FINANCIAL_CAPABILITIES:
            op_type = "financial"
        elif any(capability_id.startswith(p) for p in ("payment.", "billing.", "transfer.", "wallet.", "subscription.")):
            op_type = "financial"
        else:
            op_type = "unknown"

        steps.append(StepDefinition(
            step_id=step_id,
            capability_id=capability_id,
            capability_version=raw_step.get("capability_version", "^1.0.0"),
            depends_on=raw_step.get("depends_on", []),
            parameters=raw_step.get("parameters", {}),
            outputs_captured=raw_step.get("outputs_captured", {}),
            failure_mode=FailureMode.CONTINUE if on_failure == "continue" else FailureMode.HALT,
            retries=retries,
            retry_backoff=retry_backoff,
            retry_base_ms=retry_base_ms,
            max_cost_usd=float(max_cost),
            timeout_ms=int(timeout),
            operation_type=op_type,
        ))

    # Parse DAG
    dag = raw.get("dag", {})
    edges = []
    if isinstance(dag, dict):
        for edge in dag.get("edges", []):
            if isinstance(edge, dict) and "from" in edge and "to" in edge:
                edges.append((edge["from"], edge["to"]))
    critical_path = dag.get("critical_path", []) if isinstance(dag, dict) else []

    # Parse budget
    budget = raw.get("budget", {})
    max_total_cost = budget.get("max_total_cost_usd", MAX_TOTAL_COST_USD_DEFAULT) if isinstance(budget, dict) else MAX_TOTAL_COST_USD_DEFAULT
    per_step_enforced = budget.get("per_step_budgets_enforced", True) if isinstance(budget, dict) else True
    on_exceeded = budget.get("on_budget_exceeded", "halt_current_step") if isinstance(budget, dict) else "halt_current_step"

    # Parse timeout
    timeout_config = raw.get("timeout", {})
    total_timeout = timeout_config.get("total_ms", MAX_RECIPE_TIMEOUT_MS_DEFAULT) if isinstance(timeout_config, dict) else MAX_RECIPE_TIMEOUT_MS_DEFAULT

    recipe = RecipeDefinition(
        recipe_id=recipe_id,
        name=name,
        version=version,
        category=raw.get("category", ""),
        stability=raw.get("stability", "beta"),
        tier=raw.get("tier", "premium"),
        inputs_schema=raw.get("inputs", {}),
        outputs_schema=raw.get("outputs", {}),
        steps=steps,
        dag_edges=edges,
        critical_path=critical_path,
        max_total_cost_usd=float(max_total_cost),
        per_step_budgets_enforced=per_step_enforced,
        on_budget_exceeded=on_exceeded,
        total_timeout_ms=int(total_timeout),
    )

    # Validate at compile time
    DAGValidator.validate(recipe)

    return recipe
