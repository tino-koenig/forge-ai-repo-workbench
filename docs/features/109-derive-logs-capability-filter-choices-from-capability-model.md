# Derive Logs Capability Filter Choices from Capability Model

## Description

Use the canonical capability model as single source of truth for `forge logs --capability` accepted values.

## Addresses Issues

- [Issue 47 - Logs Capability Filter Is Hardcoded and Can Drift from Capability Model](/Users/tino/PhpstormProjects/forge/docs/issues/47-logs-capability-filter-is-hardcoded-and-can-drift-from-capability-model.md)

## Spec

- Generate CLI logs capability filter choices from `core.capability_model.Capability` values.
- Keep parser help explicit and deterministic.
- Add guard test that fails on drift between model and CLI choices.

## Definition of Done

- Adding a capability in the model automatically updates accepted `logs --capability` values.
- No duplicated hardcoded capability tuple remains for logs filter parsing.
- Regression gate catches future drift.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
