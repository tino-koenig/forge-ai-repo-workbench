# Doctor and Config Validate

## Description

This feature introduces an explicit diagnostics capability:
- `forge doctor`

`doctor` verifies Forge runtime prerequisites and configuration correctness without modifying repository state.

The capability is read-only and human-auditable by default.

## Spec

### Scope

Provide a direct command to validate:
- repository root resolution
- presence of `.forge/config.toml` and `.forge/config.local.toml`
- `.env` discovery (default or `--env-file`)
- resolved LLM provider configuration
- prompt template readability
- optional OpenAI-compatible endpoint reachability

### CLI shape

Primary command:
- `forge doctor`
- `forge config validate` (alias)

Optional controls:
- `forge doctor --check-llm-endpoint`
- `forge doctor --output-format json`

### Core rules

- `doctor` is strictly `read_only`
- no writes to repository or `.forge/`
- no hidden remediation actions
- checks are explicit and listed with status

### Status model

Each check has:
- `key`
- `status` (`pass|warn|fail`)
- `detail`
- optional `recommendation`

Overall status:
- `fail` if any check fails
- `warn` if no failure but at least one warning
- `pass` otherwise

### Network behavior

Endpoint probing is opt-in via `--check-llm-endpoint`.
Without that flag, `doctor` performs local checks only.

### Output

Text mode:
- summary
- checks list
- recommendations
- uncertainty note
- next step

JSON mode:
- standard Forge output contract
- `sections.status`
- `sections.checks[]`

## Design

### Why this feature

Feature 013 added config layering and provider integration.
`doctor` makes that setup operationally understandable and debuggable for local/dev/team environments.

### Non-goals

- no automatic fix/apply mode
- no secret printing
- no endpoint checks by default

## Definition of Done

- `forge doctor` command exists and is routed through capability model
- `doctor` is read-only and effect-bounded
- local config/env/provider checks are explicit and actionable
- optional endpoint probe works when requested
- JSON output contract includes check details
- quality gates include doctor smoke + contract coverage

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 014; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
