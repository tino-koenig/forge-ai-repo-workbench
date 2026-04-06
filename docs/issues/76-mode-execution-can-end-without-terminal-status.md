

# Mode Execution Can End Without Explicit Terminal Status

## Problem

Foundation 01 (`mode_execution_foundation`) can complete a run without setting a clear `terminal_status` in the final state.

Currently, `run_mode(...)` derives the terminal status from the `ExecutionState`. If no stage explicitly sets a terminal indicator via `state_delta`, the resulting `ExecutionOutcome` may contain:

- no explicit terminal status, or
- an implicit / `None` terminal status.

This creates ambiguity for downstream foundations that rely on a clear end-of-run signal.

## Why this matters

Foundation 01 is the execution backbone. Other foundations assume that a completed run has a well-defined terminal outcome.

If the terminal status is missing or implicit:

- Foundation 02 (Orchestration) cannot reliably interpret end states,
- Foundation 10 (Output Contract) may produce incomplete or misleading outputs,
- Foundation 11 (Observability) may derive incorrect summaries,
- error vs. success semantics become unclear.

A run must never end in a semantically undefined terminal state.

## Evidence

- `run_mode(...)` returns `ExecutionOutcome` based on final state.
- `terminal_status` is not guaranteed to be set if no stage provides it.
- Some execution paths (especially error/blocked propagation) can finish without an explicit terminal marker.

## Required behavior

- Every completed execution must have a **deterministic, explicit terminal status**.
- The terminal status must be one of a defined set (e.g. `ok`, `error`, `blocked`).
- Terminal semantics must not depend on implicit state interpretation.

## Done criteria

- `ExecutionOutcome` always contains a non-null `terminal_status`.
- A fallback mechanism exists if no stage sets it explicitly.
- The fallback is deterministic and consistent with the final execution state.
- Regression tests cover:
  - normal successful run
  - error during a stage
  - blocked execution
  - no explicit terminal status provided by stages

## Scope

This issue is limited to **terminal status semantics in Foundation 01**.
It does not require redesigning the full execution model.

## Suggested implementation direction

- Define a canonical mapping from final `ExecutionState` to `terminal_status`.
- Apply this mapping in `run_mode(...)` if no explicit terminal value is present.
- Ensure that error and blocked conditions propagate into the final status.
- Keep the behavior deterministic and independent of stage implementation details.

## How To Validate Quickly

1. Run a mode where no stage sets a terminal status.
2. Inspect the returned `ExecutionOutcome`.
3. Confirm that `terminal_status` is still set.
4. Verify that different end conditions produce consistent terminal values.

## Known Limits / Notes

- This issue does not define the full set of allowed terminal statuses; it enforces that a status must always exist.
- Downstream foundations may later tighten the allowed value set.