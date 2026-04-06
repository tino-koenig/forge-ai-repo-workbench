# Foundation Observability Duplicate Block Reasons

## Problem

Foundation observability currently overcounts blocked-action reasons because the same logical block can be aggregated more than once into `block_reasons` summaries.

In particular, `EVENT_ACTION_BLOCKED` can be counted repeatedly for the same effective block outcome, which distorts emitted summary data even when the underlying runtime behavior is correct.

## Why this matters

- Observability summaries become quantitatively wrong, not just noisy.
- Consumers may overestimate how many distinct block causes occurred in a run.
- Debugging and review workflows lose trust in summary-level telemetry.
- Metrics derived from blocked-action reasons become unstable or misleading.

## Evidence

- The current aggregation path allows the same blocked-action reason to be appended more than once.
- `EVENT_ACTION_BLOCKED` is a known example where duplicate counting can occur.
- The issue affects summary integrity even when the actual event flow and blocking decision are otherwise correct.

## Required behavior

- Each logical blocked-action reason must appear only once per canonical aggregation scope.
- Duplicate counting of the same effective reason must be prevented before final summary emission.
- Distinct reasons must still remain distinct and visible.
- Emitted summaries must stay deterministic and auditable.

## Done criteria

- Duplicate `block_reasons` entries for the same logical blocked-action reason are removed.
- `EVENT_ACTION_BLOCKED` is not double-counted for a single effective block outcome.
- Ordering remains deterministic after deduplication.
- Regression coverage includes at least:
  - duplicate blocked-action input collapsing to one emitted reason
  - multiple distinct block reasons remaining preserved
  - stable summary output ordering

## Scope

This issue is limited to Foundation observability aggregation for blocked-action reason summaries.

It does not redefine reason taxonomy, event naming, or blocking policy semantics.

## Implemented Behavior (Current)

- Run-summary derivation now deduplicates `block_reasons` by `reason_code` at aggregation time.
- Deduplication preserves deterministic first-seen ordering.
- `EVENT_ACTION_BLOCKED` no longer inflates summary reasons through duplicate aggregation paths.
- Distinct blocked-action reasons remain visible as separate entries.

## Suggested implementation direction

- Define a canonical aggregation key for blocked-action reasons.
- Deduplicate during aggregation rather than only at final formatting time.
- Preserve first-seen ordering when collapsing duplicates.
- Keep emitted summaries transparent so repeated raw events do not inflate logical reason counts.

## How To Validate Quickly

1. Trigger a run where the same blocked-action reason is introduced multiple times for one effective block outcome.
2. Inspect the emitted `block_reasons` summary.
3. Confirm that the logical reason appears once, not multiple times.
4. Confirm that genuinely different block reasons are still preserved separately.

## Known Limits / Notes

- This issue is about summary correctness, not runtime blocking behavior.
- Repeated raw events may still exist internally if appropriate; the emitted logical summary must not overcount them.
- Broader observability schema changes remain out of scope.
