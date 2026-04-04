# Schema-Aware Unknown-Key Validation for Config TOML

## Description

Add schema-aware unknown-key detection for `.forge/config.toml` and `.forge/config.local.toml`.

## Addresses Issues

- [Issue 44 - Config Validation Does Not Report Unknown Keys](/Users/tino/PhpstormProjects/forge/docs/issues/44-config-validation-does-not-report-unknown-keys.md)

## Spec

- Define allowlisted config key schema for supported config sections.
- Emit diagnostics for unknown keys with path detail and close-match suggestions.
- Surface findings in `doctor` and `config validate` outputs.

## Definition of Done

- Typo/unknown keys are detected deterministically.
- Validation results include actionable diagnostics.
- Regression tests cover unknown-key cases in both config files.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
