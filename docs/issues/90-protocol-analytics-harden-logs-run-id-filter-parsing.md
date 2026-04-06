# Protocol Analytics Harden logs_run_id Filter Parsing So Invalid Input Does Not Crash Filtering

## Problem

Protocol analytics filtering currently converts `logs_run_id` directly to integer during filter application without robust invalid-input handling.

Invalid non-numeric values can raise exceptions and crash the filtering path instead of returning a controlled validation error.

## Why this matters

- One malformed filter value can break log inspection workflows.
- Runtime robustness is reduced for scripted and programmatic callers.
- User-facing diagnostics become less actionable when the path fails with an exception instead of a precise filter error.

## Evidence

- `logs_run_id` is parsed with direct integer conversion in filter logic.
- Invalid input can raise `ValueError` during filtering.

## Required behavior

- Invalid `logs_run_id` input must be handled deterministically with a clear, controlled error path.
- Filtering must not crash because of malformed run-id filter values.
- Valid numeric filters must keep existing behavior.

## Done criteria

- Filter parsing no longer throws uncaught conversion exceptions for invalid `logs_run_id`.
- Invalid values produce explicit validation feedback.
- Existing valid filter behavior remains unchanged.
- Tests cover:
  - valid numeric run-id filtering
  - invalid run-id input handling.

## Scope

This issue is limited to `logs_run_id` filter parsing hardening in protocol analytics.

It does not include redesign of other filter parameters, event schema changes, or broader analytics output changes.

## Linked Features

- _To be defined during implementation._

## Suggested implementation direction

- Parse `logs_run_id` through a safe conversion path before list filtering.
- Return a domain-specific `ValueError` message (or existing project-standard diagnostic form) instead of uncaught conversion exceptions.

## Implemented Behavior (Current)

- Protocol analytics `apply_filters(...)` now parses `logs_run_id` via safe integer conversion before filtering.
- Invalid `--run-id` input now raises a controlled validation error (`invalid --run-id filter: expected integer`) instead of crashing through direct integer conversion.
- Valid numeric `logs_run_id` filtering semantics remain unchanged.

## How To Validate Quickly

1. Run analytics filtering with a valid numeric `logs_run_id`; verify expected subset.
2. Run filtering with invalid `logs_run_id` (for example `abc`).
3. Confirm controlled error handling and no crash.

## Known Limits / Notes

- This issue only addresses `logs_run_id` parsing robustness.
- Similar hardening for other filters can be handled separately if needed.
