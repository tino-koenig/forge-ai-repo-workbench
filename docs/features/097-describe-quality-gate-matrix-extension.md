# Describe Quality Gate Matrix Extension

## Description

Expand describe quality-gate coverage to semantic resolution and evidence-precision cases.

## Addresses Issues

- [Issue 40 - Describe Regression Coverage Misses Unresolved-Target and Symbol-Anchor Cases](/Users/tino/PhpstormProjects/forge/docs/issues/40-describe-regression-coverage-misses-unresolved-target-and-symbol-anchor-cases.md)

## Spec

- Add deterministic gates for:
  - unresolved explicit target handling
  - symbol-target evidence anchoring
  - important-file ranking noise control
  - describe contract compatibility after policy/orchestrator changes

## Definition of Done

- New describe gates are integrated into standard quality-gate execution.
- Regressions fail with clear deterministic diagnostics.

## Implemented Behavior (Current)

- Added integrated describe quality-gate matrix:
  - `gate_describe_quality_gate_matrix`
- Matrix coverage includes:
  - unresolved explicit target contract behavior
  - symbol-anchor evidence presence
  - important-file scope/ranking noise control
  - runtime-policy describe limits and source tracing
  - central orchestrator trace compatibility
- Matrix is wired into `run_all_gates` as standard execution path.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_describe_quality_gate_matrix` passes.

## Known Limits / Notes

- Matrix aggregates focused describe gates for clear deterministic failure diagnostics while retaining reusable gate granularity.
