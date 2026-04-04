# Shared Init Default-Value Foundation with Central Config

## Description

Extract overlapping init default values into a shared foundation with central config defaults to prevent drift.

## Addresses Issues

- [Issue 55 - Init Default Values Are Duplicated and Can Drift from Central Config Foundation](/Users/tino/PhpstormProjects/forge/docs/issues/55-init-default-values-are-duplicated-and-can-drift-from-central-config-foundation.md)

## Spec

- Define canonical default-value helpers/constants for overlapping planner/orchestrator settings.
- Use shared defaults in both init rendering and central config resolution.
- Keep template-specific deviations explicit in template definitions.

## Definition of Done

- Overlapping defaults are sourced from shared foundation, not duplicated literals.
- Changing canonical defaults updates init output and runtime defaults coherently.
- Drift regression tests are added.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
