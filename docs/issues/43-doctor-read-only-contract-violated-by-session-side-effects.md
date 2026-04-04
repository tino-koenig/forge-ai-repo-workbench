# Doctor Read-Only Contract Violated by Session Side Effects

## Problem

`forge doctor` is specified as read-only, but it can create/update session artifacts due to session auto-activation in CLI bootstrap.

## Evidence

- Repro:
  - remove `.forge/sessions`
  - run `python3 forge.py --repo-root <repo> --output-format json doctor`
  - observed creation of `.forge/sessions/index.json` and `auto-*.json`
- `config validate` alias path does not trigger the same write in equivalent run, creating behavior inconsistency.
- Relevant flow:
  - runtime-consuming capability set includes `doctor`
  - bootstrap calls `ensure_active_session(...)` before capability execution

## Required behavior

- Doctor/config-validate must remain strictly read-only: no session auto-create and no activity writes.
- Alias behavior (`doctor` vs `config validate`) must be semantically equivalent for side effects.

## Done criteria

- Running `doctor` does not create/modify `.forge/sessions/*`.
- `doctor` and `config validate` have consistent side-effect behavior.
- Regression gate asserts read-only behavior for both entrypoints.

## Linked Features

- [Feature 102 - Read-Only Capability Guard for Session Auto-Activation](/Users/tino/PhpstormProjects/forge/docs/features/102-read-only-capability-guard-for-session-auto-activation.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
