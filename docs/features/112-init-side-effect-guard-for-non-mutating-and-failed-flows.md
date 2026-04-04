# Init Side-Effect Guard for Non-Mutating and Failed Flows

## Description

Prevent repository mutations for init flows that are informational, preview-only, or precondition-failed.

## Addresses Issues

- [Issue 49 - Init Non-Mutating Flows Create `.forge` Marker via Run History](/Users/tino/PhpstormProjects/forge/docs/issues/49-init-non-mutating-flows-create-forge-marker-via-run-history.md)

## Spec

- Introduce explicit policy: non-mutating init outcomes must skip run-history persistence and marker creation.
- Covered flows:
  - `init --list-templates`
  - `init --dry-run`
  - precondition failures (non-tty interactive, invalid template, invalid target)
- Keep successful write-intent init behavior unchanged.

## Definition of Done

- Non-mutating and failed init flows produce no `.forge` artifacts in fresh dirs.
- Successful init still records history normally.
- Regression matrix covers all listed flows.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
