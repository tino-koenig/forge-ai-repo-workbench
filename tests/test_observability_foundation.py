from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from core.observability_foundation import (
    EVENT_ACTION_BLOCKED,
    EVENT_ACTION_EXECUTED,
    EVENT_BUDGET_EXHAUSTED,
    EVENT_BUDGET_SNAPSHOT,
    EVENT_DECISION_MADE,
    EVENT_POLICY_BLOCKED,
    EVENT_STAGE_FINISHED,
    EVENT_STAGE_STARTED,
    ObsContext,
    obs_end_run,
    obs_get_run_events,
    obs_get_run_summary,
    obs_log_event,
    obs_make_event,
    obs_reset_state,
    obs_start_run,
)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def tick(self, seconds: int = 1) -> None:
        self._now = self._now + timedelta(seconds=seconds)


class ObservabilityFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        obs_reset_state()
        self.clock = _Clock(datetime(2026, 4, 5, 10, 0, 0, tzinfo=timezone.utc))
        self.context = ObsContext(
            capability="query",
            profile="standard",
            source_component="foundation-test",
            session_id="session-1",
            parent_run_id="parent-1",
            level="minimal",
            now=self.clock.now,
        )

    def test_event_creation_contains_required_fields(self) -> None:
        run_id = obs_start_run(self.context)
        event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_STAGE_STARTED,
            payload={"stage": "scan", "debug_details": {"x": 1}},
            redaction_status="not_needed",
            stage_id="scan",
        )
        obs_log_event(event)
        event_dict = event.as_dict()
        self.assertEqual(event_dict["event_type"], EVENT_STAGE_STARTED)
        self.assertEqual(event_dict["run_id"], run_id)
        self.assertEqual(event_dict["capability"], "query")
        self.assertEqual(event_dict["profile"], "standard")
        self.assertEqual(event_dict["redaction_status"], "not_needed")
        self.assertIsInstance(event_dict["payload"], dict)
        self.assertNotIn("debug_details", event_dict["payload"])

    def test_event_correlation_fields(self) -> None:
        run_id = obs_start_run(self.context)
        event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_ACTION_EXECUTED,
            payload={"result": "ok"},
            redaction_status="not_needed",
            stage_id="execute",
            action_id="read-1",
            iteration_id="iter-1",
            decision_source="deterministic",
            policy_version="policy-1",
            settings_snapshot_id="settings-1",
            action_input_hash="input-hash-1",
            state_before={"count": 1},
            state_after={"count": 2},
        )
        obs_log_event(event)
        data = event.as_dict()
        self.assertEqual(data["run_id"], run_id)
        self.assertEqual(data["session_id"], "session-1")
        self.assertEqual(data["parent_run_id"], "parent-1")
        self.assertEqual(data["iteration_id"], "iter-1")
        self.assertTrue(isinstance(data["trace_id"], str) and data["trace_id"].startswith("trace-"))
        self.assertEqual(data["action_id"], "read-1")
        started_trace_id = obs_get_run_events(run_id)[0].trace_id
        self.assertEqual(data["trace_id"], started_trace_id)

    def test_obs_log_event_rejects_run_context_mismatch(self) -> None:
        run_id = obs_start_run(self.context)
        wrong_context = ObsContext(
            capability="review",
            profile="strict",
            source_component="other-component",
            now=self.clock.now,
        )
        event = obs_make_event(
            context=wrong_context,
            run_id=run_id,
            event_type=EVENT_STAGE_STARTED,
            payload={"stage": "scan"},
            redaction_status="not_needed",
            stage_id="scan",
        )
        with self.assertRaises(ValueError):
            obs_log_event(event)

    def test_payload_must_be_structured(self) -> None:
        run_id = obs_start_run(self.context)
        with self.assertRaises(ValueError):
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_STAGE_STARTED,
                payload="free text",  # type: ignore[arg-type]
                redaction_status="not_needed",
            )

    def test_redaction_status_applied_requires_version_and_masks_sensitive(self) -> None:
        run_id = obs_start_run(self.context)
        with self.assertRaises(ValueError):
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_STAGE_STARTED,
                payload={"api_key": "secret-value"},
                redaction_status="not_needed",
            )

        event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_STAGE_STARTED,
            payload={"api_key": "[REDACTED]"},
            redaction_status="applied",
            redaction_version="redact-v1",
        )
        obs_log_event(event)
        self.assertEqual(event.redaction_status, "applied")

    def test_event_level_separation_and_orchestration_requirements(self) -> None:
        run_id = obs_start_run(self.context)
        with self.assertRaises(ValueError):
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_ACTION_BLOCKED,
                payload={"reason_code": "policy"},
                redaction_status="not_needed",
                action_id="a1",
            )

        event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_ACTION_BLOCKED,
            payload={"reason_code": "policy"},
            redaction_status="not_needed",
            action_id="a1",
            iteration_id="iter-1",
            policy_version="policy-1",
            settings_snapshot_id="settings-1",
            action_input_hash="input-1",
        )
        obs_log_event(event)
        self.assertTrue(event.event_type.startswith("action_"))

    def test_run_summary_is_derived_from_events(self) -> None:
        run_id = obs_start_run(self.context)

        self.clock.tick(1)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_STAGE_STARTED,
                payload={"stage": "scan"},
                redaction_status="not_needed",
                stage_id="scan",
            )
        )
        self.clock.tick(2)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_STAGE_FINISHED,
                payload={"stage": "scan"},
                redaction_status="not_needed",
                stage_id="scan",
            )
        )
        self.clock.tick(1)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_DECISION_MADE,
                payload={"decision": "continue", "control_signal": "replan", "reason_code": "no_progress"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                decision_source="fallback",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )
        self.clock.tick(1)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_ACTION_BLOCKED,
                payload={"reason_code": "write_scope_denied"},
                redaction_status="not_needed",
                action_id="write",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
                action_input_hash="input-2",
            )
        )
        self.clock.tick(1)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_BUDGET_SNAPSHOT,
                payload={"budget_name": "token_budget"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )
        self.clock.tick(1)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_BUDGET_EXHAUSTED,
                payload={"budget_name": "token_budget"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )
        self.clock.tick(1)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_POLICY_BLOCKED,
                payload={"reason_code": "policy_blocked"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )

        self.clock.tick(1)
        summary = obs_end_run(run_id, {"done_reason": "policy_blocked"})

        self.assertGreaterEqual(summary.duration_ms, 0)
        self.assertEqual(summary.action_status_counts["blocked"], 1)
        self.assertIn("token_budget", summary.budget_relevant)
        self.assertIn("no_progress", summary.replan_reasons)
        self.assertIn("write_scope_denied", summary.block_reasons)
        self.assertIsNotNone(obs_get_run_summary(run_id))

    def test_replan_summary_uses_control_signal_for_continue(self) -> None:
        run_id = obs_start_run(self.context)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_DECISION_MADE,
                payload={"decision": "continue", "control_signal": "replan", "reason_code": "no_progress"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )

        summary = obs_end_run(run_id, None)
        self.assertEqual(summary.replan_reasons, ("no_progress",))

    def test_replan_summary_ignores_continue_without_replan_signal(self) -> None:
        run_id = obs_start_run(self.context)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_DECISION_MADE,
                payload={"decision": "continue", "control_signal": "none", "reason_code": "normal_progress"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )

        summary = obs_end_run(run_id, None)
        self.assertEqual(summary.replan_reasons, tuple())

    def test_replan_summary_ignores_stop_without_replan_signal(self) -> None:
        run_id = obs_start_run(self.context)
        obs_log_event(
            obs_make_event(
                context=self.context,
                run_id=run_id,
                event_type=EVENT_DECISION_MADE,
                payload={"decision": "stop", "control_signal": "none", "reason_code": "budget_exhausted"},
                redaction_status="not_needed",
                iteration_id="iter-1",
                policy_version="policy-1",
                settings_snapshot_id="settings-1",
            )
        )

        summary = obs_end_run(run_id, None)
        self.assertEqual(summary.replan_reasons, tuple())
        self.assertEqual(summary.stop_reasons, ("budget_exhausted",))

    def test_sampling_does_not_remove_required_correlation_fields(self) -> None:
        run_id = obs_start_run(self.context)
        event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_ACTION_EXECUTED,
            payload={"debug_details": {"step": 1}, "result": "ok"},
            redaction_status="not_needed",
            action_id="a1",
            iteration_id="iter-1",
            policy_version="policy-1",
            settings_snapshot_id="settings-1",
            action_input_hash="input-1",
        )
        obs_log_event(event)
        event_dict = event.as_dict()
        self.assertEqual(event_dict["run_id"], run_id)
        self.assertIsNotNone(event_dict["trace_id"])
        self.assertEqual(event_dict["iteration_id"], "iter-1")
        self.assertNotIn("debug_details", event_dict["payload"])

    def test_trace_id_is_present_and_consistent_for_non_orchestration_events(self) -> None:
        run_id = obs_start_run(self.context)
        started_trace_id = obs_get_run_events(run_id)[0].trace_id
        stage_event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_STAGE_STARTED,
            payload={"stage": "init"},
            redaction_status="not_needed",
            stage_id="init",
        )
        obs_log_event(stage_event)
        self.assertEqual(stage_event.trace_id, started_trace_id)
        self.assertIsNotNone(stage_event.trace_id)

    def test_event_structure_is_deterministic(self) -> None:
        run_id = obs_start_run(self.context)
        event = obs_make_event(
            context=self.context,
            run_id=run_id,
            event_type=EVENT_STAGE_STARTED,
            payload={"b": 2, "a": {"d": 4, "c": 3}},
            redaction_status="not_needed",
            stage_id="scan",
        )
        obs_log_event(event)
        payload_keys = list(event.as_dict()["payload"].keys())
        nested_keys = list(event.as_dict()["payload"]["a"].keys())  # type: ignore[index]
        self.assertEqual(payload_keys, ["a", "b"])
        self.assertEqual(nested_keys, ["c", "d"])

    def test_retention_prunes_closed_runs_after_window(self) -> None:
        short_context = ObsContext(
            capability="query",
            profile="standard",
            source_component="foundation-test",
            level="minimal",
            retention_seconds=2,
            now=self.clock.now,
        )
        run_id = obs_start_run(short_context)
        obs_end_run(run_id, None)
        self.assertTrue(obs_get_run_events(run_id))

        self.clock.tick(3)
        _ = obs_start_run(short_context)
        self.assertEqual(obs_get_run_events(run_id), tuple())

    def test_obs_reset_state_resets_id_counters(self) -> None:
        run_a = obs_start_run(self.context)
        self.assertEqual(run_a, "obs-run-000001")
        obs_end_run(run_a, None)
        obs_reset_state()
        run_b = obs_start_run(self.context)
        self.assertEqual(run_b, "obs-run-000001")


if __name__ == "__main__":
    unittest.main()
