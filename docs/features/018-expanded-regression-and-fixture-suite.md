# Expanded Regression and Fixture Suite

## Description

This feature expands deterministic and provider-aware regression coverage.

The goal is to reduce behavior drift while Forge adds capabilities and configuration depth.

## Spec

### Scope

Extend test fixtures and gates for:
- multiple repository shapes
- config layering edge cases
- provider success/failure permutations
- prompt template resolution failures
- fallback correctness under partial misconfiguration

### Fixture expansion

Add fixture repositories representing:
- service-oriented Python project
- frontend-heavy repository
- mixed-language repo with sparse docs
- repo with intentionally malformed config/templates for negative tests

### Quality gates expansion

New gate categories:
- precedence and override matrix checks
- LLM-off vs LLM-on contract parity checks
- deterministic fallback invariants
- doctor/config-validate scenario matrix

### Failure semantics

Each regression gate should:
- fail with precise actionable message
- identify capability and scenario context
- avoid flaky network dependencies in default CI path

## Design

### Why this feature

Forge has moved beyond simple heuristics and now includes config layering and provider logic.
Regression depth must grow with this complexity to preserve confidence.

### Non-goals

- no full external integration test matrix against every provider in this feature
- no heavy end-to-end UI testing

## Definition of Done

- at least two new fixture repos are added
- quality gates cover key config/provider edge cases
- regressions in output contracts and fallback logic are caught automatically
- CI remains deterministic and reasonably fast

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 018; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
