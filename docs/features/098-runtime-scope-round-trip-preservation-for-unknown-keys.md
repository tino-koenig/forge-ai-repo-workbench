# Runtime Scope Round-Trip Preservation for Unknown Keys

## Description

Preserve unknown/non-registry keys when writing repo/user runtime scope files via `forge set`.

## Addresses Issues

- [Issue 3 - Runtime `set` Overwrites Unknown Scope Keys](/Users/tino/PhpstormProjects/forge/docs/issues/3-runtime-set-overwrites-unknown-scope-keys.md)

## Spec

- Runtime file update must be non-destructive for unknown keys/tables.
- Known canonical key writes should merge into existing payload rather than replacing whole file content with recognized keys only.
- Deterministic formatting should remain stable.

## Definition of Done

- Unknown keys survive `forge set --scope repo|user` updates.
- Target key updates remain deterministic and auditable.
- Regression tests cover unknown-key preservation.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
