# Capability Quality Gates

## Description

This feature introduces repeatable quality gates for Forge capabilities to prevent regressions in behavior, evidence quality, and effect boundaries.

## Spec

### Scope

Define and implement quality gates for:
- query
- explain
- review
- describe
- test
- index

### Gate categories

- behavior gates
- output contract gates
- evidence quality gates
- effect boundary gates
- fallback gates (with and without index)

### Test strategy

- CLI smoke tests on fixture repos
- golden output checks for stable scenarios
- policy checks for read-only capabilities
- targeted regression tests for known edge cases

### Failure policy

- gate failures block release
- known flaky cases require explicit quarantine/justification

## Design

### Why this matters

Without explicit gates, capability behavior drifts as features evolve.

Quality gates keep Forge predictable and auditable while enabling faster iteration.

### Constraints

- tests should validate capability behavior, not implementation internals
- keep fixtures realistic but lightweight
- avoid brittle snapshots for highly variable fields

## Definition of Done

- baseline fixture repos and smoke suite exist
- regression tests cover key flows per capability
- effect boundary tests verify read-only guarantees
- index/no-index fallback behavior is tested for relevant capabilities
- CI exposes clear pass/fail signal for all gates

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 011; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
