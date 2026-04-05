from __future__ import annotations

import unittest

from core.orchestration_foundation import (
    HandoffPacket,
    IterationInput,
    ObjectiveSpec,
    OrchestrationState,
    ProgressSignal,
    apply_orchestration_step,
    choose_done_reason,
    decide_orchestration,
    evaluate_progress_signal,
    validate_fsm_transition,
)


class OrchestrationFoundationTests(unittest.TestCase):
    def _state(self, **overrides: object) -> OrchestrationState:
        base = OrchestrationState(
            run_id="run-1",
            trace_id="trace-1",
            objective=ObjectiveSpec(
                objective_id="obj-1",
                objective_type="locate_definition",
                acceptance_gates=("symbol_anchor",),
                hard_fail_gates=("policy_allow_write",),
            ),
            max_no_progress_streak=2,
            max_replans=1,
            action_repeat_limit=2,
        )
        payload = {
            "run_id": base.run_id,
            "trace_id": base.trace_id,
            "objective": base.objective,
            "lifecycle_state": base.lifecycle_state,
            "iteration_count": base.iteration_count,
            "done_reason": base.done_reason,
            "no_progress_streak": base.no_progress_streak,
            "max_no_progress_streak": base.max_no_progress_streak,
            "replan_count": base.replan_count,
            "max_replans": base.max_replans,
            "action_repeat_limit": base.action_repeat_limit,
            "action_fingerprint_counts": dict(base.action_fingerprint_counts),
            "last_state_payload": dict(base.last_state_payload),
            "handoff_loop_count": base.handoff_loop_count,
        }
        payload.update(overrides)
        return OrchestrationState(**payload)

    def test_continue_decision_with_progress(self) -> None:
        state = self._state()
        iteration = IterationInput(
            iteration_id="it-1",
            next_action="read",
            action_input_hash="h1",
            action_status="ok",
            budget_before=10.0,
            budget_after=9.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=2, confidence_gain=0.2, top_candidate_changed=True, score_gain=0.3),
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.decision, "continue")
        self.assertEqual(decision.control_signal, "none")
        self.assertEqual(decision.next_action, "read")

    def test_done_reason_priority(self) -> None:
        reason = choose_done_reason(
            {
                "sufficient_evidence": True,
                "no_progress": True,
                "budget_exhausted": False,
                "policy_blocked": True,
                "error": False,
            }
        )
        self.assertEqual(reason, "policy_blocked")

    def test_progress_no_progress_aggregation(self) -> None:
        progress = evaluate_progress_signal(
            ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0)
        )
        self.assertTrue(progress.no_progress)
        self.assertEqual(progress.confidence, "low")

    def test_fsm_transitions(self) -> None:
        ok, diag = validate_fsm_transition("initialized", "running")
        self.assertTrue(ok)
        self.assertIsNone(diag)

        ok_invalid, diag_invalid = validate_fsm_transition("terminal_success", "running")
        self.assertFalse(ok_invalid)
        self.assertIsNotNone(diag_invalid)

    def test_blocked_vs_terminal_failure(self) -> None:
        state = self._state(lifecycle_state="running")
        iteration = IterationInput(
            iteration_id="it-1",
            next_action="write",
            action_input_hash="h1",
            action_status="blocked",
            budget_before=10.0,
            budget_after=10.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0),
            policy_blocked=True,
            policy_recoverable=False,
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.decision, "stop")
        self.assertEqual(decision.done_reason, "policy_blocked")

    def test_blocked_state_is_really_reachable_for_recoverable_policy_block(self) -> None:
        state = self._state(lifecycle_state="running")
        iteration = IterationInput(
            iteration_id="it-1",
            next_action="write",
            action_input_hash="h-recoverable",
            action_status="blocked",
            budget_before=10.0,
            budget_after=10.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0),
            policy_blocked=True,
            policy_recoverable=True,
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.control_signal, "block")
        new_state, trace = apply_orchestration_step(state, iteration, decision)
        self.assertEqual(new_state.lifecycle_state, "blocked")
        self.assertEqual(trace.control_signal, "block")

    def test_recovery_from_blocked_transitions_back_to_running(self) -> None:
        state = self._state(lifecycle_state="blocked")
        iteration = IterationInput(
            iteration_id="it-2",
            next_action="write",
            action_input_hash="h-recover",
            action_status="noop",
            budget_before=8.0,
            budget_after=8.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.1, top_candidate_changed=False, score_gain=0.1),
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.control_signal, "recover")
        new_state, trace = apply_orchestration_step(state, iteration, decision)
        self.assertEqual(new_state.lifecycle_state, "running")
        self.assertTrue(trace.recovery_step)

    def test_blocked_with_unrecoverable_policy_stops_terminally(self) -> None:
        state = self._state(lifecycle_state="blocked")
        iteration = IterationInput(
            iteration_id="it-blocked-policy",
            next_action="write",
            action_input_hash="h-bp",
            action_status="blocked",
            budget_before=5.0,
            budget_after=5.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0),
            policy_blocked=True,
            policy_recoverable=False,
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.decision, "stop")
        self.assertEqual(decision.done_reason, "policy_blocked")

    def test_blocked_with_unrecoverable_budget_stops_terminally(self) -> None:
        state = self._state(lifecycle_state="blocked")
        iteration = IterationInput(
            iteration_id="it-blocked-budget",
            next_action="search",
            action_input_hash="h-bb",
            action_status="blocked",
            budget_before=1.0,
            budget_after=0.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0),
            budget_recoverable=False,
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.decision, "stop")
        self.assertEqual(decision.done_reason, "budget_exhausted")

    def test_blocked_with_logic_error_stops_terminally(self) -> None:
        state = self._state(lifecycle_state="blocked")
        iteration = IterationInput(
            iteration_id="it-blocked-error",
            next_action="read",
            action_input_hash="h-be",
            action_status="error",
            budget_before=5.0,
            budget_after=5.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0),
            failure_category="logic_error",
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.decision, "stop")
        self.assertEqual(decision.done_reason, "error")

    def test_replan_trigger_priority_keeps_objective_gate_miss(self) -> None:
        state = self._state(lifecycle_state="running", no_progress_streak=1, replan_count=0)
        iteration = IterationInput(
            iteration_id="it-3",
            next_action="read",
            action_input_hash="h-replan-prio-1",
            action_status="noop",
            budget_before=10.0,
            budget_after=9.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.01),
            objective_gate_missed=True,
            replan_candidate_action="search",
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.control_signal, "replan")
        self.assertEqual(decision.replan_trigger, "objective_gate_miss")
        self.assertTrue(any(d.code == "replan_secondary_trigger_active" for d in decision.diagnostics))

    def test_replan_trigger_priority_keeps_new_evidence_conflict(self) -> None:
        state = self._state(lifecycle_state="running", no_progress_streak=1, replan_count=0)
        iteration = IterationInput(
            iteration_id="it-3b",
            next_action="read",
            action_input_hash="h-replan-prio-2",
            action_status="noop",
            budget_before=10.0,
            budget_after=9.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.01),
            new_evidence_conflict=True,
            replan_candidate_action="rank",
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.control_signal, "replan")
        self.assertEqual(decision.replan_trigger, "new_evidence_conflict")

    def test_no_progress_streak_trigger_requires_current_no_progress_iteration(self) -> None:
        state = self._state(lifecycle_state="running", no_progress_streak=1, replan_count=0)
        iteration = IterationInput(
            iteration_id="it-progress-now",
            next_action="read",
            action_input_hash="h-progress-now",
            action_status="ok",
            budget_before=10.0,
            budget_after=9.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.2, top_candidate_changed=True, score_gain=0.1),
            replan_candidate_action="search",
        )
        decision = decide_orchestration(state, iteration)
        self.assertNotEqual(decision.control_signal, "replan")

    def test_replan_anti_loop(self) -> None:
        state = self._state(
            no_progress_streak=2,
            action_fingerprint_counts={"read:h1": 2},
            lifecycle_state="running",
        )
        iteration = IterationInput(
            iteration_id="it-3",
            next_action="read",
            action_input_hash="h1",
            action_status="noop",
            budget_before=10.0,
            budget_after=9.5,
            actual_cost=0.5,
            progress_signal=ProgressSignal(evidence_gain=0, confidence_gain=0.0, top_candidate_changed=False, score_gain=0.0),
            replan_candidate_action="search",
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.decision, "stop")
        self.assertEqual(decision.done_reason, "no_progress")

    def test_fingerprint_count_not_incremented_for_handoff_or_blocked_recover_step(self) -> None:
        state = self._state(lifecycle_state="running")
        handoff = HandoffPacket(
            handoff_id="handoff-fp",
            source_mode="fix",
            target_mode="review",
            reason="regression_check",
            constraints={},
            evidence_bundle=({"finding": "x"},),
            acceptance_gates=("no_high_findings",),
            max_loop_count=2,
        )
        iteration_handoff = IterationInput(
            iteration_id="it-handoff",
            next_action="read",
            action_input_hash="h-fp",
            action_status="ok",
            budget_before=10.0,
            budget_after=9.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.2, top_candidate_changed=False, score_gain=0.1),
            requested_handoff=handoff,
        )
        decision_handoff = decide_orchestration(state, iteration_handoff)
        state_after_handoff, _ = apply_orchestration_step(state, iteration_handoff, decision_handoff)
        self.assertEqual(state_after_handoff.action_fingerprint_counts, {})

        blocked_state = self._state(lifecycle_state="blocked")
        iteration_recover = IterationInput(
            iteration_id="it-recover",
            next_action="read",
            action_input_hash="h-fp",
            action_status="noop",
            budget_before=9.0,
            budget_after=9.0,
            actual_cost=0.0,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.2, top_candidate_changed=False, score_gain=0.1),
        )
        decision_recover = decide_orchestration(blocked_state, iteration_recover)
        state_after_recover, _ = apply_orchestration_step(blocked_state, iteration_recover, decision_recover)
        self.assertEqual(state_after_recover.action_fingerprint_counts, {})

    def test_handoff_contract(self) -> None:
        state = self._state(lifecycle_state="running")
        handoff = HandoffPacket(
            handoff_id="handoff-1",
            source_mode="fix",
            target_mode="review",
            reason="regression_check",
            constraints={"file_scope": ["a.py"]},
            evidence_bundle=({"finding": "x"},),
            acceptance_gates=("no_high_findings",),
            max_loop_count=1,
        )
        iteration = IterationInput(
            iteration_id="it-1",
            next_action=None,
            action_input_hash="handoff-hash",
            action_status="ok",
            budget_before=8.0,
            budget_after=7.5,
            actual_cost=0.5,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.1, top_candidate_changed=False, score_gain=0.2),
            requested_handoff=handoff,
        )
        decision = decide_orchestration(state, iteration)
        self.assertEqual(decision.control_signal, "handoff")

        new_state, trace = apply_orchestration_step(state, iteration, decision)
        self.assertEqual(new_state.lifecycle_state, "running")
        self.assertEqual(trace.control_signal, "handoff")
        self.assertEqual(trace.causal_parent_id, iteration.causal_parent_id)
        self.assertEqual(new_state.handoff_loop_count, 1)

    def test_handoff_loop_count_is_consecutive_chain_and_resets_on_non_handoff(self) -> None:
        state = self._state(lifecycle_state="running", handoff_loop_count=0)
        handoff = HandoffPacket(
            handoff_id="handoff-loop",
            source_mode="fix",
            target_mode="review",
            reason="loop-check",
            constraints={},
            evidence_bundle=({"finding": "x"},),
            acceptance_gates=("no_high_findings",),
            max_loop_count=3,
        )
        handoff_iteration = IterationInput(
            iteration_id="it-h1",
            next_action=None,
            action_input_hash="h-handoff",
            action_status="ok",
            budget_before=8.0,
            budget_after=7.5,
            actual_cost=0.5,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.1, top_candidate_changed=False, score_gain=0.1),
            requested_handoff=handoff,
        )
        handoff_decision = decide_orchestration(state, handoff_iteration)
        state_after_handoff, _ = apply_orchestration_step(state, handoff_iteration, handoff_decision)
        self.assertEqual(state_after_handoff.handoff_loop_count, 1)

        normal_iteration = IterationInput(
            iteration_id="it-normal",
            next_action="read",
            action_input_hash="h-normal",
            action_status="ok",
            budget_before=7.5,
            budget_after=7.0,
            actual_cost=0.5,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.2, top_candidate_changed=True, score_gain=0.2),
        )
        normal_decision = decide_orchestration(state_after_handoff, normal_iteration)
        state_after_normal, _ = apply_orchestration_step(state_after_handoff, normal_iteration, normal_decision)
        self.assertEqual(state_after_normal.handoff_loop_count, 0)

    def test_trace_is_deterministic(self) -> None:
        state = self._state(lifecycle_state="running")
        iteration = IterationInput(
            iteration_id="it-1",
            next_action="read",
            action_input_hash="same-hash",
            action_status="ok",
            budget_before=5.0,
            budget_after=4.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.2, top_candidate_changed=True, score_gain=0.2),
            settings_snapshot_id="settings-1",
            policy_version="policy-1",
        )
        decision = decide_orchestration(state, iteration)
        state_a, trace_a = apply_orchestration_step(state, iteration, decision)
        state_b, trace_b = apply_orchestration_step(state, iteration, decision)
        self.assertEqual(trace_a.state_hash_before, trace_b.state_hash_before)
        self.assertEqual(trace_a.state_hash_after, trace_b.state_hash_after)
        self.assertEqual(state_a.iteration_count, state_b.iteration_count)

    def test_trace_hash_is_stable_for_equivalent_mapping_with_different_insertion_order(self) -> None:
        state_a = self._state(
            lifecycle_state="running",
            action_fingerprint_counts={"a:h1": 1, "b:h2": 2},
        )
        state_b = self._state(
            lifecycle_state="running",
            action_fingerprint_counts={"b:h2": 2, "a:h1": 1},
        )
        iteration = IterationInput(
            iteration_id="it-hash-stable",
            next_action="read",
            action_input_hash="same-hash",
            action_status="ok",
            budget_before=5.0,
            budget_after=4.0,
            actual_cost=1.0,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.2, top_candidate_changed=True, score_gain=0.2),
            settings_snapshot_id="settings-1",
            policy_version="policy-1",
        )
        decision_a = decide_orchestration(state_a, iteration)
        decision_b = decide_orchestration(state_b, iteration)
        _, trace_a = apply_orchestration_step(state_a, iteration, decision_a)
        _, trace_b = apply_orchestration_step(state_b, iteration, decision_b)
        self.assertEqual(trace_a.state_hash_before, trace_b.state_hash_before)

    def test_trace_exposes_decision_diagnostic_codes(self) -> None:
        state = self._state(
            lifecycle_state="running",
            no_progress_streak=0,
            action_fingerprint_counts={"read:h1": 2},
            max_no_progress_streak=3,
        )
        iteration = IterationInput(
            iteration_id="it-diag-trace",
            next_action="read",
            action_input_hash="h1",
            action_status="noop",
            budget_before=5.0,
            budget_after=4.5,
            actual_cost=0.5,
            progress_signal=ProgressSignal(evidence_gain=1, confidence_gain=0.1, top_candidate_changed=False, score_gain=0.1),
        )
        decision = decide_orchestration(state, iteration)
        _, trace = apply_orchestration_step(state, iteration, decision)
        self.assertIn("replan_anti_loop_exhausted", trace.decision_diagnostic_codes)


if __name__ == "__main__":
    unittest.main()
