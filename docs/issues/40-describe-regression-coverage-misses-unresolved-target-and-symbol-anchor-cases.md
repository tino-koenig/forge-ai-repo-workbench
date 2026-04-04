# Describe Regression Coverage Misses Unresolved-Target and Symbol-Anchor Cases

## Problem

Current quality gates cover baseline contract shape for describe but miss critical semantic correctness cases.

## Evidence

- Existing gates validate describe JSON structure and fixture language extraction.
- No gate for explicit unresolved target behavior.
- No gate for symbol-target evidence anchoring.
- No gate for important-file ranking noise in fixture-heavy repos.

## Required behavior

- Add describe gate matrix covering semantic resolution and evidence precision behaviors.

## Done criteria

- New gates cover:
  - unresolved explicit target contract
  - symbol-anchor evidence presence
  - important-file ranking/next-step noise control
- Regressions fail deterministically with clear messages.

## Linked Features

- [Feature 097 - Describe Quality Gate Matrix Extension](/Users/tino/PhpstormProjects/forge/docs/features/097-describe-quality-gate-matrix-extension.md)

## Implemented Behavior (Current)

- Describe regressions now include a dedicated matrix gate (`gate_describe_quality_gate_matrix`).
- The matrix enforces:
  - explicit unresolved-target contract
  - symbol-anchor evidence behavior
  - important-file ranking noise control
  - runtime policy application and source tracing
  - orchestrator-trace compatibility
- Matrix is integrated into standard quality-gate execution.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_describe_quality_gate_matrix` passes.

## Known Limits / Notes

- Coverage remains deterministic and fixture-based, complementing broader smoke tests.
