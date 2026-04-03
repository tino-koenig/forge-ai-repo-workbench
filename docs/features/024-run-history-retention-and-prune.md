# Run History Retention and Prune

## Description

This feature adds explicit lifecycle management for run history.

Forge currently appends run records but does not rotate or prune history.
This feature introduces configurable retention and manual prune commands.

## Spec

### Scope

Add history management capabilities for `.forge/runs.jsonl`:
- retention configuration
- manual prune command
- dry-run preview mode

### CLI shape

Primary commands:
- `forge runs prune`
- `forge runs prune --keep-last 200`
- `forge runs prune --older-than-days 30`
- `forge runs prune --dry-run`

Optional future extension:
- `forge runs compact` for rewrite/defragmentation without semantic changes

### Retention policy

Configurable defaults in `.forge/config.toml`:
- `runs.retention.keep_last`
- `runs.retention.max_age_days`
- `runs.retention.max_file_mb` (soft threshold warning)

Precedence:
1. CLI flags
2. config values
3. safe defaults

### Safety constraints

- prune is explicit; no hidden auto-delete in this feature
- `--dry-run` must show how many entries would be removed
- prune operation must preserve valid JSONL format
- corrupted lines should be reported and skipped safely

### Output

Text mode:
- before/after counts
- deleted count
- retention criteria used

JSON mode:
- counts
- criteria
- affected id ranges

## Design

### Why this feature

History growth is useful for traceability but unmanaged growth can become noisy and heavy.
Explicit retention preserves control and predictability.

### Non-goals

- no background daemon for automatic cleanup
- no external database migration in this feature

## Definition of Done

- `forge runs prune` exists with dry-run support
- retention config is read and validated
- prune rewrites history safely and deterministically
- quality gates cover:
  - no-op prune
  - dry-run output
  - actual prune with expected remaining entries

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 024; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
