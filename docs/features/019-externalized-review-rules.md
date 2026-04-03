# Externalized Review Rules

## Description

This feature moves selected review heuristics into explicit, versioned rule configuration.

The objective is to make review behavior easier to adapt across repositories while preserving auditability.

## Spec

### Scope

Support rule-driven extensions for `forge review`:
- pattern-based findings
- severity configuration
- recommendation templates
- optional file/path scope constraints

Rules are loaded from repo-local config (for example `.forge/review-rules.toml`).

### Rule model (initial)

Each rule defines:
- `id`
- `title`
- `severity` (`low|medium|high`)
- `pattern` (regex)
- optional `path_includes` / `path_excludes`
- `explanation`
- optional `recommendation`

### Evaluation behavior

- built-in core heuristics remain active
- external rules add findings, not hidden control flow
- rule matches require concrete evidence lines
- invalid rules are surfaced via `doctor` and skipped safely

### Safety constraints

- no code execution from rule files
- no network lookups from rules
- no dynamic prompt injection through rules

## Design

### Why this feature

Review quality varies by codebase conventions.
Externalized rules enable controlled adaptation without hardcoding every project-specific pattern.

### Non-goals

- no full rule DSL or scripting engine
- no automatic rule generation from LLM output

## Definition of Done

- review can load and apply external rule file
- invalid rules are reported clearly and do not crash review
- findings include rule identifier for auditability
- quality gates cover at least one custom rule success case and one invalid rule case

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 019; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
