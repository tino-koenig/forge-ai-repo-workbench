# Index Contract and Observability Doctor

## Description

This feature introduces deterministic diagnostics for index contract health, including producer/consumer consistency checks.

Goal:
- make index quality and contract drift visible,
- help operators detect why index-aware retrieval behaves unexpectedly,
- keep debugging local and auditable.

## Spec

### New diagnostics surface

Extend doctor/status tooling with index contract checks:
- index schema/version validity,
- path-class distribution,
- index participation counts,
- consumer consistency checks (for example retrieval scope honoring index participation),
- graph/index synchronization status and warnings.

### Output

Provide concise human output and structured JSON diagnostics for automation.

## Design

### Why this feature

When index exists but outcomes are noisy, users currently need deep code inspection. A first-class doctor surface reduces guesswork.

### Non-goals

- no auto-fixing of repository code
- no hidden mutation outside `.forge/`

## Definition of Done

- Doctor command exposes index contract diagnostics in text and JSON views.
- At least one check validates producer/consumer path-class consistency.
- Fail/warn states are actionable and reference concrete files/fields.

## Implemented Behavior (Current)

- `forge index` now persists graph-failure observability metadata in `.forge/index.json`:
  - `graph.warning` is written when graph build is skipped due to an exception.
- Regression coverage includes a deterministic forced-failure path that validates warning persistence in the index artifact.
- This closes the index/graph observability gap where console warning existed but persisted index metadata stayed stale.

## How To Validate Quickly

1. Run the quality-gate check that forces graph-build failure during index execution:
   - `python3 scripts/run_quality_gates.py`
2. Verify the `gate_index_persists_graph_build_warning` step passes.
3. In the test scenario, confirm `.forge/index.json` contains `graph.warning` after the forced graph failure.

## Known Limits / Notes

- Full doctor/status index-contract paneling is broader than this increment; this implementation focuses on persisted graph-warning contract correctness for index artifacts.
