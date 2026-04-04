# Config Validation Passes While Provider-Required Fields Are Missing

## Problem

`config_validation` can pass even when provider-required fields are missing (for example `openai_compatible` without `base_url`/`model`).

## Evidence

- `forge init --template balanced` creates config with `provider=openai_compatible` but without `base_url`/`model`.
- `doctor` shows:
  - `config_validation: pass`
  - `llm_base_url: fail`
  - `llm_model: fail`
- This splits validation semantics and weakens clarity of config health.

## Required behavior

- Provider-required field checks should be integrated into config validation semantics (or a clearly separated mandatory check group with consistent status impact).
- Validation status must not communicate "pass" when required provider fields are absent.

## Done criteria

- Missing provider-required fields fail config validation (or equivalent mandatory group) deterministically.
- `doctor` and `config validate` report consistent validation outcomes and messaging.
- Regression tests cover initialized-config and explicit-missing-field cases.

## Linked Features

- [Feature 104 - Mandatory Provider Field Validation Harmonization](/Users/tino/PhpstormProjects/forge/docs/features/104-mandatory-provider-field-validation-harmonization.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
