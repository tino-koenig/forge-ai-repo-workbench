# Orchestration Foundation Parallel Core Bootstrap

## Description

Implement Foundation 02 as a new parallel core orchestration foundation with deterministic continue/stop decisions, explicit done-reasons, progress aggregation, replan/recovery/handoff signals, FSM transition checks, and deterministic iteration traces.

## Spec

- Add typed orchestration models:
  - `OrchestrationDecision`
  - `ProgressSignal` / `ProgressEvaluation`
  - `OrchestrationDiagnostic`
  - `OrchestrationState`
- Add deterministic orchestration APIs:
  - `decide_orchestration(state, iteration)`
  - `evaluate_progress_signal(signal)`
  - `validate_fsm_transition(current, next, ...)`
  - `apply_orchestration_step(state, iteration, decision)`
- Enforce done-reason priority:
  - `error > policy_blocked > budget_exhausted > no_progress > sufficient_evidence`
- Enforce anti-loop/replan constraints and structured handoff contract.
- Emit deterministic, structured per-iteration orchestration trace with forensic anchors.

## Definition of Done

- Core module exists in `core/orchestration_foundation.py`.
- Continue/stop decisions are deterministic and test-covered.
- Progress/no-progress aggregation is centralized and deterministic.
- FSM transition checks and blocked-vs-terminal behavior are explicit and test-covered.
- Replan anti-loop and handoff contract are implemented and test-covered.
- Iteration trace schema is deterministic and test-covered.

## Implemented Behavior (Current)

- Added deterministic orchestration core with explicit typed contracts.
- Added done-reason prioritization helper and centralized progress aggregation policy.
- Added finite-state transition validator for allowed orchestration lifecycle transitions.
- Added deterministic decision function supporting `control_signal` values:
  - `none | replan | recover | handoff | block`
- Added anti-loop logic via action/input fingerprint limits and replan budget.
- Added structured handoff packet contract with required fields and loop-limit handling.
- Added deterministic trace entries with:
  - run/trace/iteration references
  - decision + confidence + control signal
  - budget before/after
  - progress score/components
  - action/state/settings/policy forensic anchors

## How To Validate Quickly

1. Run `python3 -m unittest tests/test_orchestration_foundation.py`.
2. Verify:
   - continue vs stop behavior
   - done-reason priority
   - no-progress aggregation
   - FSM transition enforcement
   - blocked vs terminal handling
   - replan anti-loop stop
   - handoff signal/contract behavior
   - deterministic trace hashes

## Known Limits / Notes

- This is a parallel core implementation and is not yet integrated into active mode runtime loops.
- LLM-assisted decisioning remains intentionally outside this foundation core (deterministic baseline only).
- Full multi-step orchestration runner over mode execution plans is intentionally deferred; foundation currently provides reusable decision/state/trace primitives.
