

# Observability Summary Misreads Replan as a Decision Instead of a Control Signal

## Problem

Foundation 11 currently derives replan-related summary information from `decision == "replan"`.
However, Foundation 02 defines `decision` as only:

- `continue`
- `stop`

Replan is not a decision value. It is expressed through:

- `control_signal = "replan"`

This means Observability is currently misreading the Orchestration contract and can silently produce incorrect run summaries.

## Why this matters

Forge relies on Observability to answer not just what happened, but why a run behaved as it did.
If replan is interpreted from the wrong field:

- summaries become semantically incorrect,
- debugging becomes misleading,
- orchestration behavior may look healthier or simpler than it really was,
- later analytics and reporting can draw false conclusions.

This is a cross-foundation contract violation between Foundation 02 and Foundation 11.

## Evidence

- Foundation 02 models:
  - `decision ∈ {continue, stop}`
  - `control_signal ∈ {none, replan, recover, handoff, block}`
- Foundation 11 summary derivation currently checks for replan via `decision == "replan"`.
- As a result, real replan events may not be captured correctly in run summaries.

## Required behavior

- Foundation 11 must interpret replan from `control_signal`, not from `decision`.
- Summary derivation must stay fully aligned with the normative Orchestration contract from Foundation 02.
- Replan-related summary counts or flags must reflect actual replan events emitted by the orchestration layer.

## Done criteria

- Replan summary derivation in Foundation 11 reads `control_signal == "replan"`.
- No logic in Foundation 11 assumes `decision == "replan"`.
- Regression tests cover at least:
  - `continue + replan`
  - `continue + no replan`
  - `stop` without replan
- Summary output changes only where the previous behavior was contractually wrong.

## Scope

This issue is about the semantic alignment between Foundation 02 and Foundation 11.
It does not require redesigning the overall Observability event model.

## Suggested implementation direction

- Audit summary derivation in `core/observability_foundation.py` for all replan-related logic.
- Replace any `decision == "replan"` checks with the correct `control_signal`-based logic.
- Add regression tests that express the Foundation 02 contract explicitly.
- Optionally review similar control-signal handling for `recover`, `handoff` and `block` while keeping this issue focused on replan.

## How To Validate Quickly

1. Emit an orchestration event with:
   - `decision="continue"`
   - `control_signal="replan"`
2. End the run and inspect the derived summary.
3. Confirm that the run is reported as having replanned.
4. Confirm that `decision="stop"` without replan does not count as a replan.

## Known Limits / Notes

- This issue is not about event emission itself, only about how Foundation 11 derives summary semantics from already emitted orchestration events.
- Similar cross-foundation contract audits may be useful after this fix, but are outside the scope of this issue.