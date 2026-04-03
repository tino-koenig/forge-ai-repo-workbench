# From-Run References Across Capabilities

## Description

This feature enables direct capability workflows from run history IDs.

Instead of manually copying context from `forge runs show`, users can execute:
- `forge explain --from-run 12`
- `forge review --from-run 12`
- `forge test --from-run 12`
- `forge describe --from-run 12`

The command resolves target context from stored run records and launches the requested capability directly.

## Spec

### Scope

Extend capability CLIs with run-reference input:
- `forge explain --from-run <id>`
- `forge review --from-run <id>`
- `forge test --from-run <id>`
- `forge describe --from-run <id>`

Supported run sources (initial):
- query runs (top likely location)
- review runs (top finding evidence path)
- describe runs (resolved target path if available)
- test runs (resolved target path if available)

### Resolution rules

Given run ID:
1. load history record
2. validate record type and output structure
3. extract best resolvable target path/symbol/context
4. run requested capability with resolved input payload

If resolution fails:
- return explicit actionable error with reason
- suggest `forge runs <id> show full`

### CLI behavior

Allowed forms:
- `forge explain --from-run 12`
- `forge review --from-run 12`
- `forge test detailed --from-run 12`
- `forge explain detailed --from-run 12`

Conflicts:
- if both direct target and `--from-run` are provided, fail with clear message

### Output transparency

Capability output should include:
- `source_run_id`
- `source_run_capability`
- `resolved_from_run_strategy`
- `resolved_from_run_payload`

JSON output should expose same fields in sections metadata.

### Safety constraints

- no write effects
- no hidden fallback to arbitrary files
- resolution must be deterministic and auditable

## Design

### Why this feature

Run-history references become significantly more useful when multiple downstream capabilities can consume them directly.
This reduces manual copy/paste and keeps workflows composable.

### Non-goals

- no cross-repo run reference resolution
- no implicit rerun of the source record during resolution

## Definition of Done

- `--from-run` is supported by explain/review/test/describe
- run types are resolved to capability inputs deterministically
- errors are explicit for unsupported or malformed records
- output includes run-reference provenance metadata
- quality gates cover:
  - success path from query run id into explain/review
  - success path from review run id into explain/test
  - success path from describe/test run id into explain
  - failure path for invalid id or unsupported record

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 025; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
