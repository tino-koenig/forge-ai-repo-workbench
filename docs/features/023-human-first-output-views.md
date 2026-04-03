# Human-First Output Views

## Description

This feature improves human readability by introducing explicit output views for stored run results:
- `compact`
- `standard`
- `full`

The goal is to reduce noise in default human inspection workflows while preserving full detail on demand.

## Spec

### Scope

For `forge runs show` and related forms:
- `compact` shows minimal key signal
- `standard` shows summary + essential metadata
- `full` shows complete captured output

### CLI shape

Supported positional forms:
- `forge runs show 12 compact`
- `forge runs 12 show full`
- `forge runs 12 standard`

### Behavior

- view selection must not trigger re-execution
- output rendering is based on stored run data only
- rerun remains explicit (`forge runs 12 rerun`)

### JSON behavior

`--output-format json` returns full stored run record, independent of text view modes.

## Design

### Why this feature

Forge outputs can be rich and verbose.
View modes allow fast human scanning without losing auditability.

### Non-goals

- no lossy mutation of stored history records
- no hidden auto-rerun to produce alternate views

## Definition of Done

- view modes are supported with positional syntax
- compact and standard views are clearly distinguishable from full
- history view switching never re-executes capability logic
- quality gates cover show/rerun behavior

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 023; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
