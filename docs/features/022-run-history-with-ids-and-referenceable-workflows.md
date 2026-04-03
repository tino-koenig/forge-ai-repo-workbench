# Run History with IDs and Referenceable Workflows

## Description

This feature introduces persistent run history with stable IDs.

Users can reference previous results directly in follow-up workflows, for example:
- `forge runs 12 show full`
- `forge runs 12 rerun`
- `forge runs last --output-format json`

## Spec

### Scope

Persist executed capability runs in:
- `.forge/runs.jsonl`

Each entry contains:
- run id
- timestamp
- request metadata (capability/profile/payload)
- execution metadata (exit code/output format)
- captured output (text + optional JSON contract)

### CLI surface

Add `forge runs` command family:
- `forge runs list`
- `forge runs last`
- `forge runs show <id> [compact|standard|full]`
- `forge runs <id> show [compact|standard|full]`
- `forge runs <id> rerun`

### Reference model

Runs are repository-local and ordered by execution.
ID assignment is monotonic in the history file.

### Constraints

- no secrets persisted in history payloads
- no hidden mutation effects from reading history
- rerun is explicit and opt-in

## Definition of Done

- run history file is created and appended automatically
- runs can be listed, shown, and rerun by id
- `runs last --output-format json` returns machine-consumable record
- quality gates validate history creation and rerun path

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 022; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
