# Stale Ask Logic Remains in Query and CLI Wording

## Problem

Ask was split into dedicated capability, but query still contains legacy ask-preset logic and CLI help text still says ask "maps to query".

Observed behavior:
- `modes/query.py` contains `apply_ask_preset(...)` and ask-specific warnings.
- CLI help string for `ask` claims mapping to query, although runtime routes to `Capability.ASK`.

This increases cognitive load and risks behavior drift between ask and query paths.

## Required behavior

- Remove/retire legacy ask-only logic from query where no longer needed.
- Align CLI help and docs with current ask capability architecture.

## Done criteria

- Query no longer contains obsolete ask-preset compatibility flow.
- CLI/help text reflects dedicated ask mode accurately.
- Regression checks ensure command routing remains explicit and correct.

## Linked Features

- [076-ask-query-boundary-cleanup.md](/Users/tino/PhpstormProjects/forge/docs/features/076-ask-query-boundary-cleanup.md)

## Implemented Behavior (Current)

- Query mode no longer contains obsolete ask-only preset/filter compatibility paths.
- CLI help text for `forge ask` reflects dedicated ask capability routing.
- A regression gate (`gate_ask_query_boundary_cleanup`) verifies explicit ask/query boundary behavior.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_ask_query_boundary_cleanup` passes.

## Known Limits / Notes

- The boundary cleanup intentionally does not change ask internals; it removes only stale query-side compatibility behavior and wording drift.
