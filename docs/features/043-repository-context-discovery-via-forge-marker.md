# Repository Context Discovery via Forge Marker

## Description

This feature defines how Forge resolves the active repository context by locating a `.forge` marker directory.

Primary goals:
- deterministic repo resolution
- intuitive behavior in nested directory structures
- explicit failure when no initialized context exists

## Spec

### Scope

Forge resolves repository context by walking upward from current working directory and selecting the nearest ancestor containing `.forge/`.

Resolution rule:
- nearest ancestor `.forge/` wins
- no marker found -> explicit error with initialization guidance

### Behavior outside initialized repos

When no `.forge/` marker is found, Forge should:
- fail fast with clear explanation
- suggest running `forge init` in target repo root

Optional future extension (not required here):
- explicit `--repo <path>` override

### Constraints

- no ambiguous multi-root heuristics
- no hidden global fallback repo
- no machine-local default repo that bypasses marker discovery

## Design

### Why this feature

Forge is repo-first. Marker-based nearest-ancestor resolution is simple, explicit, and easy to reason about for users and teams.

## Definition of Done

- context resolver follows nearest-ancestor `.forge/` policy
- missing marker path produces actionable error
- nested path behavior is covered by tests and docs

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 043; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
