from __future__ import annotations

import unittest

from core.mode_execution_foundation import (
    ExecutionContext,
    ExecutionState,
    ModeExecutionPlan,
    StageDefinition,
    StageDiagnostic,
    StageResult,
    apply_stage_result,
    run_mode,
)


class _Clock:
    def __init__(self) -> None:
        self._value = 1_000

    def now_ms(self) -> int:
        self._value += 5
        return self._value


def _context(clock: _Clock | None = None) -> ExecutionContext:
    active_clock = clock or _Clock()
    return ExecutionContext(
        request={"mode": "x"},
        settings={"k": "v"},
        settings_snapshot_id="settings-1",
        budget_state_ref={"tokens": 1000},
        obs_context={"trace": "enabled"},
        contract_context={"version": "1"},
        run_id="run-1",
        trace_id="trace-1",
        iteration_id="iter-1",
        now_ms=active_clock.now_ms,
    )


class ModeExecutionFoundationTests(unittest.TestCase):
    def test_plan_requires_init_and_finalize_contract(self) -> None:
        def _handler(_ctx, _state):
            return StageResult("x", "x", "ok", "none")

        with self.assertRaises(ValueError):
            ModeExecutionPlan(
                mode_name="bad",
                stages=(StageDefinition("collect", "s1", "read", _handler),),
            )

        with self.assertRaises(ValueError):
            ModeExecutionPlan(
                mode_name="bad",
                stages=(
                    StageDefinition("init", "s1", "none", _handler),
                    StageDefinition("collect", "s2", "read", _handler),
                ),
            )

    def test_stage_order_init_finalize_and_trace(self) -> None:
        order: list[str] = []

        def init_handler(_ctx, _state):
            order.append("init")
            return StageResult(
                stage_name="init",
                stage_id="s-init",
                status="ok",
                side_effect_class="none",
            )

        def analyze_handler(_ctx, _state):
            order.append("analyze")
            return StageResult(
                stage_name="analyze",
                stage_id="s-analyze",
                status="ok",
                side_effect_class="read",
            )

        def finalize_handler(_ctx, _state):
            order.append("finalize")
            return StageResult(
                stage_name="finalize",
                stage_id="s-finalize",
                status="ok",
                side_effect_class="none",
            )

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("analyze", "s-analyze", "read", analyze_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )

        outcome = run_mode(plan, _context(_Clock()))

        self.assertEqual(order, ["init", "analyze", "finalize"])
        self.assertEqual([r.stage_name for r in outcome.stage_results], ["init", "analyze", "finalize"])
        self.assertEqual([t.stage_name for t in outcome.trace], ["init", "analyze", "finalize"])
        self.assertTrue(all(t.duration_ms == 5 for t in outcome.trace))

    def test_finalize_best_effort_runs_after_error_and_blocks_rest(self) -> None:
        called: list[str] = []

        def init_handler(_ctx, _state):
            called.append("init")
            return StageResult("init", "s-init", "ok", "none")

        def fail_handler(_ctx, _state):
            called.append("collect")
            return StageResult(
                stage_name="collect",
                stage_id="s-collect",
                status="error",
                side_effect_class="read",
                diagnostics=(StageDiagnostic(code="boom", message="failed"),),
            )

        def skipped_handler(_ctx, _state):
            called.append("analyze")
            return StageResult("analyze", "s-analyze", "ok", "read")

        def finalize_handler(_ctx, _state):
            called.append("finalize")
            return StageResult("finalize", "s-finalize", "ok", "none")

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("collect", "s-collect", "read", fail_handler),
                StageDefinition("analyze", "s-analyze", "read", skipped_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )

        outcome = run_mode(plan, _context(_Clock()))

        self.assertEqual(called, ["init", "collect", "finalize"])
        self.assertEqual(outcome.stage_results[2].status, "blocked")
        self.assertEqual(outcome.stage_results[2].diagnostics[0].code, "stage_skipped_upstream_error")
        self.assertEqual(outcome.stage_results[3].stage_name, "finalize")

    def test_skip_diagnostic_distinguishes_upstream_blocked(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult("init", "s-init", "ok", "none")

        def blocked_handler(_ctx, _state):
            return StageResult("collect", "s-collect", "blocked", "read")

        def skipped_handler(_ctx, _state):
            return StageResult("analyze", "s-analyze", "ok", "read")

        def finalize_handler(_ctx, _state):
            return StageResult("finalize", "s-finalize", "ok", "none")

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("collect", "s-collect", "read", blocked_handler),
                StageDefinition("analyze", "s-analyze", "read", skipped_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )

        outcome = run_mode(plan, _context(_Clock()))
        self.assertEqual(outcome.stage_results[2].status, "blocked")
        self.assertEqual(outcome.stage_results[2].diagnostics[0].code, "stage_skipped_upstream_blocked")

    def test_closed_status_space_enforced(self) -> None:
        with self.assertRaises(ValueError):
            StageResult("init", "s-init", "partial", "none")  # type: ignore[arg-type]

    def test_state_delta_partial_mergeable(self) -> None:
        state = ExecutionState(
            domain_state={"a": 1, "nested": {"x": 1}},
            iteration_state={"i": 1},
        )
        result = StageResult(
            stage_name="collect",
            stage_id="s-collect",
            status="ok",
            side_effect_class="read",
            state_delta={
                "domain_state": {"b": 2, "nested": {"y": 2}},
                "iteration_state": {"j": 2},
            },
        )

        merged = apply_stage_result(state, result)
        self.assertEqual(merged.domain_state["a"], 1)
        self.assertEqual(merged.domain_state["b"], 2)
        self.assertEqual(merged.domain_state["nested"], {"x": 1, "y": 2})
        self.assertEqual(merged.iteration_state, {"i": 1, "j": 2})

    def test_undeclared_stage_result_is_rejected(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult("init", "s-init", "ok", "none")

        def bad_handler(_ctx, _state):
            return StageResult("hidden", "s-hidden", "ok", "read")

        def finalize_handler(_ctx, _state):
            return StageResult("finalize", "s-finalize", "ok", "none")

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("analyze", "s-analyze", "read", bad_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )
        outcome = run_mode(plan, _context(_Clock()))

        self.assertEqual(outcome.stage_results[1].status, "error")
        self.assertEqual(outcome.stage_results[1].diagnostics[0].code, "undeclared_stage_result")

    def test_side_effect_class_mismatch_is_rejected(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult("init", "s-init", "ok", "none")

        def mismatch_handler(_ctx, _state):
            return StageResult("analyze", "s-analyze", "ok", "write")

        def finalize_handler(_ctx, _state):
            return StageResult("finalize", "s-finalize", "ok", "none")

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("analyze", "s-analyze", "read", mismatch_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )
        outcome = run_mode(plan, _context(_Clock()))

        self.assertEqual(outcome.stage_results[1].status, "error")
        self.assertEqual(outcome.stage_results[1].diagnostics[0].code, "side_effect_class_mismatch")

    def test_section_contributions_are_forwarded(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult("init", "s-init", "ok", "none")

        def synth_handler(_ctx, _state):
            return StageResult(
                stage_name="synthesize",
                stage_id="s-synth",
                status="ok",
                side_effect_class="none",
                section_contributions={"summary": ("a",), "evidence": ("b",)},
            )

        def finalize_handler(_ctx, _state):
            return StageResult(
                stage_name="finalize",
                stage_id="s-finalize",
                status="ok",
                side_effect_class="none",
                section_contributions={"summary": ("c",)},
            )

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("synthesize", "s-synth", "none", synth_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )
        outcome = run_mode(plan, _context(_Clock()))

        self.assertEqual(outcome.state.section_contributions["summary"], ("a", "c"))
        self.assertEqual(outcome.state.section_contributions["evidence"], ("b",))

    def test_stage_status_does_not_force_terminal_status(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult("init", "s-init", "ok", "none")

        def blocked_handler(_ctx, _state):
            return StageResult("collect", "s-collect", "blocked", "read")

        def finalize_handler(_ctx, _state):
            return StageResult("finalize", "s-finalize", "ok", "none")

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("collect", "s-collect", "read", blocked_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )

        outcome = run_mode(plan, _context(_Clock()))
        self.assertIsNone(outcome.terminal_status)
        self.assertIsNone(outcome.done_reason)
        self.assertEqual(outcome.stage_results[-1].stage_name, "finalize")

    def test_finalize_cannot_invent_domain_state(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult(
                stage_name="init",
                stage_id="s-init",
                status="ok",
                side_effect_class="none",
                state_delta={"domain_state": {"seed": 1}},
            )

        def finalize_handler(_ctx, _state):
            return StageResult(
                stage_name="finalize",
                stage_id="s-finalize",
                status="ok",
                side_effect_class="none",
                state_delta={"domain_state": {"invented": 99}},
            )

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )

        outcome = run_mode(plan, _context(_Clock()))
        self.assertEqual(outcome.state.domain_state, {"seed": 1})

    def test_trace_is_minimal_and_deterministic_for_same_input(self) -> None:
        def init_handler(_ctx, _state):
            return StageResult("init", "s-init", "ok", "none", state_delta={"domain_state": {"a": 1}})

        def collect_handler(_ctx, _state):
            return StageResult(
                "collect",
                "s-collect",
                "ok",
                "read",
                budget_delta={"tokens": 10},
                diagnostics=(StageDiagnostic(code="d1", message="info"),),
            )

        def finalize_handler(_ctx, _state):
            return StageResult("finalize", "s-finalize", "ok", "none")

        plan = ModeExecutionPlan(
            mode_name="demo",
            stages=(
                StageDefinition("init", "s-init", "none", init_handler),
                StageDefinition("collect", "s-collect", "read", collect_handler),
                StageDefinition("finalize", "s-finalize", "none", finalize_handler),
            ),
        )

        first = run_mode(plan, _context(_Clock()))
        second = run_mode(plan, _context(_Clock()))
        self.assertEqual(first.trace, second.trace)
        self.assertEqual(first.trace[1].state_delta_summary, tuple())
        self.assertEqual(first.trace[1].budget_delta_summary, ("tokens",))
        self.assertEqual(first.trace[1].diagnostics_count, 1)


if __name__ == "__main__":
    unittest.main()
