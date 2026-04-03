# Shared Analysis Primitives

## Description

This feature consolidates repeated analysis logic used by Query, Explain, Review, Describe, and Test Drafting into explicit shared primitives.

The goal is to reduce drift and keep capability behavior consistent without introducing hidden orchestration.

## Spec

### Scope

Create shared internal primitives for:
- target resolution (path or symbol)
- repository scanning (read-only)
- index loading and safe fallback
- evidence extraction helpers
- related-file discovery
- common ranking helpers

### Boundaries

- primitives are internal and explicit
- primitives must not perform writes
- primitives must not execute shell commands implicitly
- capability-specific behavior remains in capability modules

### API shape

Each primitive should use explicit inputs and outputs:
- input context (repo root, request profile, target/question)
- output data objects (resolved target, evidence list, candidates)
- explicit uncertainty fields where applicable

### Migration target

Capabilities to migrate to shared primitives:
- query
- explain
- review
- describe
- test

## Design

### Why this matters

Current capabilities already share similar logic patterns. Without consolidation, behavior and heuristics diverge over time.

Shared primitives preserve consistency while keeping the user-facing capabilities explicit.

### Constraints

- no monolithic agent loop
- no hidden side effects
- no loss of per-capability explicitness

## Definition of Done

- shared primitive module(s) exist and are documented
- query/explain/review/describe/test use these primitives where appropriate
- duplicated logic is reduced meaningfully
- behavior remains read-only and auditable
- capability outputs stay capability-specific

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 008; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
