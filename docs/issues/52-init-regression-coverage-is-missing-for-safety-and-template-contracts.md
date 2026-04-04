# Init Regression Coverage Is Missing for Safety and Template Contracts

## Problem

Quality gates currently do not include dedicated init coverage for critical contracts:
- non-mutating flows
- overwrite safety
- template output contracts
- init-to-doctor coherence

## Evidence

- No `gate_*` function for init-specific scenarios found in `scripts/run_quality_gates.py`.
- Existing gates cover many other features in depth but not init behavior matrix.

## Required behavior

- Add explicit init gate matrix for deterministic safety and onboarding contracts.
- Ensure regression catches side effects and template drift.

## Done criteria

- Dedicated init gates exist and run in standard quality-gate execution.
- Matrix includes dry-run/list/invalid-target/non-tty/overwrite/template variants.
- Failures are actionable with clear gate messages.

## Linked Features

- [Feature 115 - Init Quality-Gate Matrix for Safety and Template Contracts](/Users/tino/PhpstormProjects/forge/docs/features/115-init-quality-gate-matrix-for-safety-and-template-contracts.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
