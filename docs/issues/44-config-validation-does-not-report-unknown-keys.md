# Config Validation Does Not Report Unknown Keys

## Problem

Unknown keys in `.forge/config.toml` are silently ignored. Typoed keys degrade behavior but pass `config_validation`.

## Evidence

- Repro config:
  - `[llm]`
  - `providr = "openai_compatible"` (typo)
- `doctor` output:
  - `config_validation = pass`
  - `llm_provider = warn (no LLM provider configured)`
- No explicit unknown-key diagnostic is emitted.

## Required behavior

- Config validation should report unknown/unsupported keys (at least as warn, preferably fail in strict validation mode).
- Diagnostics should point to probable intended keys.

## Done criteria

- Unknown key diagnostics are emitted deterministically with path/key detail.
- `doctor`/`config validate` expose these findings in checks.
- Regression coverage includes typo-key scenarios.

## Linked Features

- [Feature 103 - Schema-Aware Unknown-Key Validation for Config TOML](/Users/tino/PhpstormProjects/forge/docs/features/103-schema-aware-unknown-key-validation-for-config-toml.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
