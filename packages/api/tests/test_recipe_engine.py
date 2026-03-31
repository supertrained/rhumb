"""Tests for Recipe Execution Engine — DAG, budget, parameter resolution (WU-42.1)."""

from __future__ import annotations

import pytest

from services.recipe_engine import (
    BudgetTracker,
    DAGValidationError,
    DAGValidator,
    FailureMode,
    ParameterResolver,
    RecipeDefinition,
    RecipeEngine,
    RecipeExecution,
    RecipeStatus,
    StepDefinition,
    StepExecutor,
    StepResult,
    StepStatus,
    compile_recipe,
    MAX_FAN_OUT,
    MAX_STEPS_PER_RECIPE,
)

from typing import Any


# ── Test helpers ──────────────────────────────────────────────────────


def _step(
    step_id: str = "s1",
    capability_id: str = "test.cap",
    depends_on: list[str] | None = None,
    failure_mode: FailureMode = FailureMode.HALT,
    retries: int = 0,
    max_cost_usd: float = 1.0,
    parameters: dict[str, Any] | None = None,
    outputs_captured: dict[str, str] | None = None,
) -> StepDefinition:
    return StepDefinition(
        step_id=step_id,
        capability_id=capability_id,
        depends_on=depends_on or [],
        failure_mode=failure_mode,
        retries=retries,
        max_cost_usd=max_cost_usd,
        parameters=parameters or {},
        outputs_captured=outputs_captured or {},
    )


_SENTINEL_STEPS = object()


def _recipe(
    steps: list[StepDefinition] | object = _SENTINEL_STEPS,
    edges: list[tuple[str, str]] | None = None,
    max_total_cost_usd: float = 10.0,
    per_step_enforced: bool = True,
    recipe_id: str = "test_recipe",
) -> RecipeDefinition:
    return RecipeDefinition(
        recipe_id=recipe_id,
        name="Test Recipe",
        version="1.0.0",
        steps=[_step()] if steps is _SENTINEL_STEPS else steps,
        dag_edges=edges or [],
        max_total_cost_usd=max_total_cost_usd,
        per_step_budgets_enforced=per_step_enforced,
    )


class MockStepExecutor(StepExecutor):
    """Mock executor that returns configurable results per step."""

    def __init__(self, results: dict[str, StepResult] | None = None) -> None:
        self._results = results or {}
        self._calls: list[tuple[str, dict]] = []

    async def execute_step(
        self,
        step: StepDefinition,
        resolved_params: dict[str, Any],
        credential_mode: str = "rhumb_managed",
    ) -> StepResult:
        self._calls.append((step.step_id, resolved_params))
        if step.step_id in self._results:
            return self._results[step.step_id]
        return StepResult(
            step_id=step.step_id,
            status=StepStatus.SUCCEEDED,
            outputs={"result": f"output_{step.step_id}"},
            cost_usd=0.01,
            receipt_id=f"rcpt_{step.step_id}",
        )


# ── DAG Validator ─────────────────────────────────────────────────────


class TestDAGValidator:
    def test_simple_linear_dag(self):
        recipe = _recipe(
            steps=[
                _step("a"),
                _step("b", depends_on=["a"]),
                _step("c", depends_on=["b"]),
            ],
            edges=[("a", "b"), ("b", "c")],
        )
        order = DAGValidator.validate(recipe)
        assert order == ["a", "b", "c"]

    def test_parallel_dag(self):
        recipe = _recipe(
            steps=[
                _step("a"),
                _step("b"),
                _step("c", depends_on=["a", "b"]),
            ],
        )
        order = DAGValidator.validate(recipe)
        assert "c" == order[-1]
        assert set(order[:2]) == {"a", "b"}

    def test_diamond_dag(self):
        recipe = _recipe(
            steps=[
                _step("a"),
                _step("b", depends_on=["a"]),
                _step("c", depends_on=["a"]),
                _step("d", depends_on=["b", "c"]),
            ],
        )
        order = DAGValidator.validate(recipe)
        assert order[0] == "a"
        assert order[-1] == "d"

    def test_cycle_detection(self):
        recipe = _recipe(
            steps=[
                _step("a", depends_on=["b"]),
                _step("b", depends_on=["a"]),
            ],
        )
        with pytest.raises(DAGValidationError, match="Cycle detected"):
            DAGValidator.validate(recipe)

    def test_self_cycle(self):
        recipe = _recipe(
            steps=[_step("a", depends_on=["a"])],
        )
        with pytest.raises(DAGValidationError, match="Cycle detected"):
            DAGValidator.validate(recipe)

    def test_missing_dependency(self):
        recipe = _recipe(
            steps=[_step("a", depends_on=["nonexistent"])],
        )
        with pytest.raises(DAGValidationError, match="unknown step"):
            DAGValidator.validate(recipe)

    def test_empty_recipe(self):
        recipe = _recipe(steps=[])
        with pytest.raises(DAGValidationError, match="no steps"):
            DAGValidator.validate(recipe)

    def test_duplicate_step_ids(self):
        recipe = _recipe(
            steps=[_step("a"), _step("a")],
        )
        with pytest.raises(DAGValidationError, match="Duplicate"):
            DAGValidator.validate(recipe)

    def test_too_many_steps(self):
        steps = [_step(f"s{i}") for i in range(MAX_STEPS_PER_RECIPE + 1)]
        recipe = _recipe(steps=steps)
        with pytest.raises(DAGValidationError, match="exceeds maximum"):
            DAGValidator.validate(recipe)

    def test_fan_out_exceeded(self):
        root = _step("root")
        children = [_step(f"c{i}", depends_on=["root"]) for i in range(MAX_FAN_OUT + 1)]
        recipe = _recipe(steps=[root] + children)
        with pytest.raises(DAGValidationError, match="fan-out"):
            DAGValidator.validate(recipe)

    def test_fan_out_at_limit_passes(self):
        root = _step("root")
        children = [_step(f"c{i}", depends_on=["root"]) for i in range(MAX_FAN_OUT)]
        recipe = _recipe(steps=[root] + children)
        order = DAGValidator.validate(recipe)
        assert order[0] == "root"
        assert len(order) == MAX_FAN_OUT + 1

    def test_invalid_dag_edge_reference(self):
        recipe = _recipe(
            steps=[_step("a")],
            edges=[("a", "nonexistent")],
        )
        with pytest.raises(DAGValidationError, match="unknown step"):
            DAGValidator.validate(recipe)


# ── Parameter Resolver ────────────────────────────────────────────────


class TestParameterResolver:
    def test_resolve_input_ref(self):
        params = {"url": {"$ref": "inputs.audio_url"}}
        inputs = {"audio_url": "https://example.com/audio.mp3"}
        resolved = ParameterResolver.resolve(params, inputs, {})
        assert resolved["url"] == "https://example.com/audio.mp3"

    def test_resolve_step_output_ref(self):
        params = {"text": {"$ref": "steps.transcribe.outputs.transcript_text"}}
        step_outputs = {"transcribe": {"transcript_text": "Hello world"}}
        resolved = ParameterResolver.resolve(params, {}, step_outputs)
        assert resolved["text"] == "Hello world"

    def test_resolve_static_values(self):
        params = {"language": "en", "format": "text"}
        resolved = ParameterResolver.resolve(params, {}, {})
        assert resolved == {"language": "en", "format": "text"}

    def test_resolve_mixed(self):
        params = {
            "url": {"$ref": "inputs.audio_url"},
            "language": "en",
            "prev_output": {"$ref": "steps.s1.outputs.result"},
        }
        inputs = {"audio_url": "https://example.com/a.mp3"}
        step_outputs = {"s1": {"result": "some text"}}
        resolved = ParameterResolver.resolve(params, inputs, step_outputs)
        assert resolved["url"] == "https://example.com/a.mp3"
        assert resolved["language"] == "en"
        assert resolved["prev_output"] == "some text"

    def test_resolve_missing_input(self):
        params = {"url": {"$ref": "inputs.nonexistent"}}
        resolved = ParameterResolver.resolve(params, {}, {})
        assert resolved["url"] is None

    def test_resolve_missing_step_output(self):
        params = {"text": {"$ref": "steps.missing.outputs.data"}}
        resolved = ParameterResolver.resolve(params, {}, {})
        assert resolved["text"] is None

    def test_unresolvable_ref_raises(self):
        params = {"x": {"$ref": "garbage.path"}}
        with pytest.raises(ValueError, match="Unresolvable"):
            ParameterResolver.resolve(params, {}, {})


# ── Budget Tracker ────────────────────────────────────────────────────


class TestBudgetTracker:
    def test_within_budget(self):
        bt = BudgetTracker(max_total_usd=1.0, per_step_enforced=True, on_exceeded="halt")
        step = _step(max_cost_usd=0.50)
        assert bt.check_step_budget(step, 0.30) is True

    def test_step_over_budget(self):
        bt = BudgetTracker(max_total_usd=1.0, per_step_enforced=True, on_exceeded="halt")
        step = _step(max_cost_usd=0.10)
        assert bt.check_step_budget(step, 0.20) is False

    def test_total_over_budget(self):
        bt = BudgetTracker(max_total_usd=0.50, per_step_enforced=True, on_exceeded="halt")
        bt.record_spend(0.40)
        step = _step(max_cost_usd=1.0)
        assert bt.check_step_budget(step, 0.20) is False

    def test_per_step_not_enforced(self):
        bt = BudgetTracker(max_total_usd=1.0, per_step_enforced=False, on_exceeded="halt")
        step = _step(max_cost_usd=0.01)
        # Even though estimate > step max, per_step not enforced
        assert bt.check_step_budget(step, 0.50) is True

    def test_remaining(self):
        bt = BudgetTracker(max_total_usd=1.0, per_step_enforced=True, on_exceeded="halt")
        bt.record_spend(0.30)
        assert bt.remaining_usd == pytest.approx(0.70)


# ── Recipe Engine ─────────────────────────────────────────────────────


class TestRecipeEngine:
    @pytest.mark.asyncio
    async def test_simple_linear_execution(self):
        recipe = _recipe(
            steps=[
                _step("a"),
                _step("b", depends_on=["a"]),
                _step("c", depends_on=["b"]),
            ],
        )
        executor = MockStepExecutor()
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.status == RecipeStatus.COMPLETED
        assert len(result.step_results) == 3
        assert all(
            sr.status == StepStatus.SUCCEEDED
            for sr in result.step_results.values()
        )
        # Verify execution order
        call_order = [c[0] for c in executor._calls]
        assert call_order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        recipe = _recipe(
            steps=[
                _step("a"),
                _step("b"),
                _step("c", depends_on=["a", "b"]),
            ],
        )
        executor = MockStepExecutor()
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.status == RecipeStatus.COMPLETED
        call_order = [c[0] for c in executor._calls]
        assert call_order[-1] == "c"

    @pytest.mark.asyncio
    async def test_halt_on_failure(self):
        recipe = _recipe(
            steps=[
                _step("a", failure_mode=FailureMode.HALT),
                _step("b", depends_on=["a"]),
            ],
        )
        executor = MockStepExecutor(results={
            "a": StepResult(
                step_id="a", status=StepStatus.FAILED, error="Provider error"
            ),
        })
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.status == RecipeStatus.FAILED
        assert result.step_results["a"].status == StepStatus.FAILED
        assert result.step_results["b"].status == StepStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_continue_on_failure(self):
        recipe = _recipe(
            steps=[
                _step("a", failure_mode=FailureMode.CONTINUE),
                _step("b"),  # b has no dependency on a
            ],
        )
        executor = MockStepExecutor(results={
            "a": StepResult(
                step_id="a", status=StepStatus.FAILED, error="Non-fatal"
            ),
        })
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.status == RecipeStatus.PARTIAL
        assert result.step_results["a"].status == StepStatus.FAILED
        assert result.step_results["b"].status == StepStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_budget_exceeded_halts(self):
        recipe = _recipe(
            steps=[
                _step("a", max_cost_usd=0.01),
                _step("b", depends_on=["a"], max_cost_usd=0.01),
            ],
            max_total_cost_usd=0.01,
        )
        executor = MockStepExecutor(results={
            "a": StepResult(
                step_id="a", status=StepStatus.SUCCEEDED,
                outputs={}, cost_usd=0.01,
            ),
        })
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.step_results["b"].status == StepStatus.BUDGET_EXCEEDED
        assert result.status == RecipeStatus.BUDGET_EXCEEDED

    @pytest.mark.asyncio
    async def test_parameter_binding(self):
        recipe = _recipe(
            steps=[
                _step("transcribe", parameters={"url": {"$ref": "inputs.audio_url"}}),
                _step(
                    "summarize",
                    depends_on=["transcribe"],
                    parameters={"text": {"$ref": "steps.transcribe.outputs.result"}},
                ),
            ],
        )
        executor = MockStepExecutor()
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {"audio_url": "https://example.com/a.mp3"})

        assert result.status == RecipeStatus.COMPLETED
        # Check first step received the input ref
        assert executor._calls[0] == ("transcribe", {"url": "https://example.com/a.mp3"})
        # Second step received the output ref from first step
        assert executor._calls[1] == ("summarize", {"text": "output_transcribe"})

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        call_count = {"a": 0}

        class RetryExecutor(StepExecutor):
            async def execute_step(self, step, params, cred_mode="rhumb_managed"):
                call_count["a"] += 1
                if call_count["a"] < 3:
                    return StepResult(step_id="a", status=StepStatus.FAILED, error="transient")
                return StepResult(step_id="a", status=StepStatus.SUCCEEDED, outputs={}, cost_usd=0.01)

        recipe = _recipe(steps=[_step("a", retries=2)])
        engine = RecipeEngine(step_executor=RetryExecutor())
        result = await engine.execute(recipe, {})

        assert result.status == RecipeStatus.COMPLETED
        assert result.step_results["a"].retries_used == 2
        assert call_count["a"] == 3

    @pytest.mark.asyncio
    async def test_retries_exhausted(self):
        class FailExecutor(StepExecutor):
            async def execute_step(self, step, params, cred_mode="rhumb_managed"):
                return StepResult(step_id=step.step_id, status=StepStatus.FAILED, error="always fails")

        recipe = _recipe(steps=[_step("a", retries=2)])
        engine = RecipeEngine(step_executor=FailExecutor())
        result = await engine.execute(recipe, {})

        assert result.status == RecipeStatus.FAILED
        assert result.step_results["a"].retries_used == 2

    @pytest.mark.asyncio
    async def test_dag_validation_failure(self):
        recipe = _recipe(
            steps=[
                _step("a", depends_on=["b"]),
                _step("b", depends_on=["a"]),
            ],
        )
        engine = RecipeEngine()
        result = await engine.execute(recipe, {})
        assert result.status == RecipeStatus.FAILED
        assert "Cycle detected" in (result.error or "")

    @pytest.mark.asyncio
    async def test_cost_tracking(self):
        recipe = _recipe(
            steps=[
                _step("a"),
                _step("b", depends_on=["a"]),
            ],
        )
        executor = MockStepExecutor(results={
            "a": StepResult(step_id="a", status=StepStatus.SUCCEEDED, cost_usd=0.05, outputs={}),
            "b": StepResult(step_id="b", status=StepStatus.SUCCEEDED, cost_usd=0.03, outputs={}),
        })
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.total_cost_usd == pytest.approx(0.08)

    @pytest.mark.asyncio
    async def test_execution_id_and_timestamps(self):
        recipe = _recipe(steps=[_step("a")])
        engine = RecipeEngine(step_executor=MockStepExecutor())
        result = await engine.execute(recipe, {})

        assert result.execution_id.startswith("rexec_")
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at

    @pytest.mark.asyncio
    async def test_skip_deps_failed(self):
        """Steps with failed dependencies are skipped even in continue mode."""
        recipe = _recipe(
            steps=[
                _step("a", failure_mode=FailureMode.CONTINUE),
                _step("b", depends_on=["a"]),  # Should be skipped even though a is continue
            ],
        )
        executor = MockStepExecutor(results={
            "a": StepResult(step_id="a", status=StepStatus.FAILED, error="oops"),
        })
        engine = RecipeEngine(step_executor=executor)
        result = await engine.execute(recipe, {})

        assert result.step_results["b"].status == StepStatus.SKIPPED
        assert "dependency" in (result.step_results["b"].error or "").lower()


# ── Recipe compiler ───────────────────────────────────────────────────


class TestCompileRecipe:
    def test_compile_minimal(self):
        raw = {
            "recipe_id": "test",
            "name": "Test",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "s1",
                    "capability_id": "test.cap",
                }
            ],
        }
        recipe = compile_recipe(raw)
        assert recipe.recipe_id == "test"
        assert len(recipe.steps) == 1
        assert recipe.steps[0].step_id == "s1"

    def test_compile_full_spec_example(self):
        raw = {
            "recipe_id": "transcribe_and_summarize_and_email",
            "name": "Transcribe, Summarize & Email",
            "version": "2.1.0",
            "category": "productivity",
            "stability": "stable",
            "tier": "premium",
            "inputs": {"type": "object", "required": ["audio_url"]},
            "outputs": {"type": "object"},
            "steps": [
                {
                    "step_id": "transcribe",
                    "capability_id": "transcribe_audio",
                    "depends_on": [],
                    "parameters": {"audio_url": {"$ref": "inputs.audio_url"}},
                    "outputs_captured": {"transcript_text": "result.transcript"},
                    "failure_mode": {"on_failure": "halt", "retries": 2},
                    "budget": {"max_cost_usd": 0.10, "timeout_ms": 60000},
                },
                {
                    "step_id": "summarize",
                    "capability_id": "summarize_text",
                    "depends_on": ["transcribe"],
                    "parameters": {"text": {"$ref": "steps.transcribe.outputs.transcript_text"}},
                    "failure_mode": {"on_failure": "halt", "retries": 1},
                    "budget": {"max_cost_usd": 0.05},
                },
                {
                    "step_id": "notify",
                    "capability_id": "send_email",
                    "depends_on": ["summarize"],
                    "parameters": {"to": {"$ref": "inputs.recipient_email"}},
                    "failure_mode": {"on_failure": "continue", "retries": 3},
                    "budget": {"max_cost_usd": 0.01},
                },
            ],
            "dag": {
                "edges": [
                    {"from": "transcribe", "to": "summarize"},
                    {"from": "summarize", "to": "notify"},
                ],
                "critical_path": ["transcribe", "summarize", "notify"],
            },
            "budget": {
                "max_total_cost_usd": 0.50,
                "per_step_budgets_enforced": True,
                "on_budget_exceeded": "halt_current_step",
            },
        }
        recipe = compile_recipe(raw)
        assert recipe.recipe_id == "transcribe_and_summarize_and_email"
        assert len(recipe.steps) == 3
        assert recipe.steps[0].retries == 2
        assert recipe.steps[2].failure_mode == FailureMode.CONTINUE
        assert recipe.max_total_cost_usd == 0.50

    def test_compile_cycle_rejected(self):
        raw = {
            "recipe_id": "bad",
            "steps": [
                {"step_id": "a", "capability_id": "x", "depends_on": ["b"]},
                {"step_id": "b", "capability_id": "x", "depends_on": ["a"]},
            ],
        }
        with pytest.raises(DAGValidationError):
            compile_recipe(raw)

    def test_compile_missing_recipe_id(self):
        with pytest.raises(ValueError, match="recipe_id"):
            compile_recipe({"steps": [{"step_id": "a", "capability_id": "x"}]})

    def test_compile_missing_capability_id(self):
        with pytest.raises(ValueError, match="capability_id"):
            compile_recipe({
                "recipe_id": "test",
                "steps": [{"step_id": "a"}],
            })
