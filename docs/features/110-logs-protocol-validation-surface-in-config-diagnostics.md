# Logs Protocol Validation Surface in Config Diagnostics

## Description

Extend central config validation/doctor diagnostics to include `logs.protocol` settings with explicit error reporting.

## Addresses Issues

- [Issue 48 - Logs Protocol Settings Are Not Validated by Doctor or Config Validate](/Users/tino/PhpstormProjects/forge/docs/issues/48-logs-protocol-settings-are-not-validated-by-doctor-or-config-validate.md)

## Spec

- Add `logs.protocol` fields to deterministic config validation rules:
  - `max_file_size_bytes`
  - `max_event_age_days`
  - `max_events_count`
  - `allow_full_prompt_until`
- Fail validation on out-of-range/invalid values instead of silent-only clamping.
- Expose diagnostics in both `doctor` and `config validate` outputs.

## Definition of Done

- Invalid `logs.protocol` values are surfaced as validation failures/warnings with clear guidance.
- `doctor` and `config validate` remain consistent for malformed logs settings.
- Regression gate includes malformed logs config matrix.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
