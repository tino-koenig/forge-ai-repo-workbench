# Human-First Default Output

## Description

This feature makes Forge default output easier to scan for humans.

Current outputs can be technically rich but visually dense.
The default mode should prioritize fast comprehension while keeping full detail available on demand.

## Spec

### Scope

Apply a human-first default rendering policy to user-facing capability output:
- query
- explain
- review
- describe
- test
- doctor

### Output modes

Introduce explicit view modes:
- `compact` (very short)
- `standard` (human-first default)
- `full` (detailed diagnostics/evidence dump)

Default:
- text output uses `standard`
- JSON output remains full contract (machine-first)

### Standard mode structure

Required order:
1. one-line summary
2. top actionable items (limited count)
3. next step
4. short uncertainty note (if relevant)

Hidden by default (moved to full/details):
- extensive evidence lists
- full LLM usage metadata block
- large ranking tables

### Full/details access

Users can explicitly request detail via:
- `--view full` (or equivalent command-form in `runs show`)
- `--details`
- `--output-format json`

### Behavior constraints

- no information loss in system (full detail still available)
- no additional writes/effects
- deterministic no-LLM output should remain stable in meaning

## Design

### Why this feature

Forge should be understandable in daily use without forcing users to parse verbose technical sections each run.

### Non-goals

- no removal of evidence/provenance from JSON contracts
- no hidden re-execution to produce alternate views

## Definition of Done

- default text output is noticeably shorter and clearer
- full detail remains accessible explicitly
- documentation shows when to use each view
- quality gates include at least one readability snapshot check per core capability

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 026; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
