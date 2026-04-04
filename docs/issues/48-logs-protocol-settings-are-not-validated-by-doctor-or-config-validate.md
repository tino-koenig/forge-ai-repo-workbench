# Logs Protocol Settings Are Not Validated by Doctor or Config Validate

## Problem

Invalid `logs.protocol` values are silently clamped at write time and do not fail validation checks.
This hides misconfiguration and weakens operator trust in diagnostics.

## Evidence

- Repro config:
  - `[logs.protocol]`
  - `max_events_count = -1`
  - `max_event_age_days = 0`
  - `max_file_size_bytes = 1`
- `forge --output-format json doctor` still reports `config_validation = pass`.
- Current behavior in `core/protocol_log.py` clamps values to minimums instead of surfacing validation errors.

## Required behavior

- `doctor` / `config validate` must validate `logs.protocol` ranges and report invalid values explicitly.
- Runtime should avoid silent correction without operator-visible diagnostics.

## Done criteria

- Invalid logs protocol settings produce deterministic validation findings.
- Validation messaging includes offending key/path and expected range.
- Regression tests cover malformed logs protocol config.

## Linked Features

- [Feature 110 - Logs Protocol Validation Surface in Config Diagnostics](/Users/tino/PhpstormProjects/forge/docs/features/110-logs-protocol-validation-surface-in-config-diagnostics.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
