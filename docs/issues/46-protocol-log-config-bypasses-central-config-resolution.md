# Protocol Log Config Bypasses Central Config Resolution

## Problem

Protocol log settings are loaded by a local TOML reader that reads only `.forge/config.toml`.
This bypasses the central config-resolution behavior (including `.forge/config.local.toml` precedence and shared validation semantics).

## Evidence

- `core/protocol_log.py` reads only `.forge/config.toml` in `_read_protocol_log_config(...)`.
- Repro:
  - `.forge/config.toml`: `logs.protocol.max_events_count = 100`
  - `.forge/config.local.toml`: `logs.protocol.max_events_count = 1`
  - after multiple runs, active `events.jsonl` still contains many lines (`>1`), proving local override is ignored.

## Required behavior

- Protocol-log settings must use the same central config pipeline as other runtime settings.
- `.forge/config.local.toml` must be able to override repo defaults for logs behavior.
- Validation and source-tracing should be consistent with the central config contract.

## Done criteria

- Logs retention/redaction settings are resolved via a shared config foundation.
- Local override precedence works for logs settings.
- Regression coverage includes a config-local override scenario for logs protocol settings.

## Linked Features

- [Feature 108 - Centralized Logs Protocol Settings in Config Foundation](/Users/tino/PhpstormProjects/forge/docs/features/108-centralized-logs-protocol-settings-in-config-foundation.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
