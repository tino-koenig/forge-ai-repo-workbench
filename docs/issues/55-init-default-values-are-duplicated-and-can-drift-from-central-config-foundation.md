# Init Default Values Are Duplicated and Can Drift from Central Config Foundation

## Problem

Init renders several config defaults as literals that are also defined in central config defaults.
This duplication can drift and produce inconsistent baseline behavior across init-generated repos and runtime defaults.

## Evidence

- `modes/init.py` renders planner/orchestrator numeric defaults as literals.
- `core/config.py` also defines canonical defaults/ranges for the same settings.
- There is no shared source ensuring init output stays aligned when defaults evolve.

## Required behavior

- Use a shared default-value foundation for generated init config where values overlap with central config defaults.
- Keep template-specific overrides explicit while deriving common defaults centrally.

## Done criteria

- No duplicated literal defaults remain for overlapping planner/orchestrator baseline settings.
- Init output and central defaults stay aligned by construction.
- Regression test guards against drift.

## Linked Features

- [Feature 118 - Shared Init Default-Value Foundation with Central Config](/Users/tino/PhpstormProjects/forge/docs/features/118-shared-init-default-value-foundation-with-central-config.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
