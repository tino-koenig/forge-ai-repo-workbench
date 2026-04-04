# Read-Only Capability Guard for Session Auto-Activation

## Description

Prevent session auto-create/activity writes for strictly read-only diagnostic capabilities.

## Addresses Issues

- [Issue 43 - Doctor Read-Only Contract Violated by Session Side Effects](/Users/tino/PhpstormProjects/forge/docs/issues/43-doctor-read-only-contract-violated-by-session-side-effects.md)

## Spec

- Introduce explicit policy to skip session auto-activation for read-only diagnostics (`doctor`, `config validate`).
- Ensure alias entrypoints share identical side-effect behavior.
- Keep session behavior unchanged for runtime-consuming analysis capabilities that are allowed to update session context.

## Definition of Done

- `doctor` and `config validate` produce no session writes.
- Behavior is consistent across both command entrypoints.
- Regression gates assert no `.forge/sessions/*` mutations.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
