# Describe Policy Thresholds and Scan Limits Are Hardcoded

## Problem

Describe uses hardcoded limits and thresholds for scan scope and output shaping, without runtime settings exposure.

## Evidence

- Examples in `modes/describe.py`:
  - framework hint scan limit (`80` / `25`)
  - language list cap (`6`)
  - component caps (`6`, `8`, `10`)
  - symbol extraction cap (`8`)
- Runtime settings registry has no describe-specific keys.

## Required behavior

- Describe policy knobs should be runtime-configurable via canonical settings with source tracing.
- Deterministic defaults must remain stable.

## Done criteria

- Canonical describe settings keys exist for major limits/caps.
- Effective value + source inspection is available via `forge get --source`.
- Regression tests cover default and overridden describe policy behavior.

## Linked Features

- [Feature 096 - Describe Runtime Settings Surface for Analysis Policy](/Users/tino/PhpstormProjects/forge/docs/features/096-describe-runtime-settings-surface-for-analysis-policy.md)

## Implemented Behavior (Current)

- Describe analysis limits are now runtime-configurable through canonical describe policy keys.
- Describe now emits source-traceable policy metadata in `sections.describe_policy`.
- Runtime overrides now deterministically affect describe output shaping (components, symbols, important files).
- Regression coverage added via `gate_describe_runtime_policy_settings`.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_describe_runtime_policy_settings` passes.

## Known Limits / Notes

- Simple-profile framework-hint scanning keeps an additional conservative cap for stability.
