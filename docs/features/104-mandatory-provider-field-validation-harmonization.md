# Mandatory Provider Field Validation Harmonization

## Description

Unify config-validation semantics so provider-required fields are part of mandatory validation status.

## Addresses Issues

- [Issue 45 - Config Validation Passes While Provider-Required Fields Are Missing](/Users/tino/PhpstormProjects/forge/docs/issues/45-config-validation-passes-while-provider-required-fields-are-missing.md)

## Spec

- Treat required provider fields (`base_url`, `model`, key reference) as mandatory validation when provider is configured.
- Keep diagnostics explicit and non-secretive.
- Align `doctor` and `config validate` reporting/status logic.

## Definition of Done

- Missing required provider fields cannot result in `config_validation: pass`.
- `doctor` and `config validate` report consistent mandatory validation status.
- Regression tests cover init-generated and malformed provider configurations.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
