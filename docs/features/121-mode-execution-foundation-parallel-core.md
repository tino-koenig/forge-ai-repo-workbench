# Mode Execution Foundation Parallel Core Bootstrap

## Description

Implement Foundation 01 as a new parallel core mode-execution skeleton with declarative stage plans, typed stage contracts, best-effort finalization, and deterministic minimal trace output.

## Spec

- Add typed execution contracts: `ExecutionContext`, `ExecutionState`, `StageResult`, `ModeExecutionPlan`, `ExecutionOutcome`.
- Enforce declarative stage plan invariants (`init` first, `finalize` last, exactly once each).
- Execute only declared stages; reject undeclared stage identity results.
- Use closed stage status space: `ok|noop|blocked|error`.
- Keep `state_delta` partial and mergeable.
- Run `finalize` best effort after upstream `error|blocked`.
- Carry `section_contributions` forward instead of final sections.
- Emit deterministic minimal trace entries per stage.

## Definition of Done

- `run_mode(plan, context)` works with typed contracts and trace output.
- Stage plan invariants are validated.
- Best-effort `finalize` and skipped-stage tracing are covered by tests.
- Contract tests cover status-space, state merge, section contribution forwarding, hidden-stage prohibition, and deterministic trace output.

## Implemented Behavior (Current)

- Added parallel foundation module `core/mode_execution_foundation.py`.
- Added stage-plan validation and a runner that executes declared stages in order.
- Added strict stage-result identity checks to prevent hidden extra stages.
- Added best-effort `finalize` and blocked skip results for skipped stages.
- Added partial state merge logic and section-contribution forwarding.
- Added structured minimal trace (`run_id`, `trace_id`, `iteration_id`, `stage_name`, `stage_id`, `status`, `duration_ms`, delta summaries, diagnostics count, settings snapshot id).

## How To Validate Quickly

1. Run `python3 -m unittest tests/test_mode_execution_foundation.py`.
2. Verify init/finalize ordering and best-effort finalize behavior on blocked/error paths.
3. Verify deterministic trace output and stage-result contract invariants.

## Known Limits / Notes

- This implementation is intentionally parallel and not wired into existing modes.
- Terminal-status prioritization and orchestration policy resolution remain intentionally delegated to Foundation 02.
