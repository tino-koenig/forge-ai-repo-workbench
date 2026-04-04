# Centralized Logs Protocol Settings in Config Foundation

## Description

Move logs protocol settings to the shared config foundation so precedence, validation, and source semantics are consistent.

## Addresses Issues

- [Issue 46 - Protocol Log Config Bypasses Central Config Resolution](/Users/tino/PhpstormProjects/forge/docs/issues/46-protocol-log-config-bypasses-central-config-resolution.md)

## Spec

- Add logs protocol settings to central config resolution (including local override support).
- Replace local direct-TOML parsing in protocol log writer with resolved config usage.
- Expose settings/source diagnostics consistently in doctor/config-validate surfaces.

## Definition of Done

- Logs settings respect `.forge/config.local.toml` precedence.
- Validation diagnostics cover logs protocol limits/values.
- Regression tests prove precedence and retention behavior under resolved config.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
