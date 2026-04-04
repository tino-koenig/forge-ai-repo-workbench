# Runtime `set` Overwrites Unknown Scope Keys

## Problem

`forge set --scope repo|user ...` rewrites the full target runtime file from recognized canonical keys only.
Unknown or future keys in the same file are silently removed.

Observed behavior:
- Existing custom table/keys in `.forge/runtime.toml` are lost after one `forge set`.
- This also drops non-registry values that should survive round-trips.

## Required behavior

- `forge set` must preserve unknown keys when updating repo/user runtime scope files.
- Updating one setting must not delete unrelated existing settings.
- Runtime settings writes should remain deterministic and inspectable.

## Done criteria

- Repro with pre-existing unknown keys keeps those keys after `forge set`.
- `forge set` updates target keys without destructive rewrite side effects.
- Add/extend quality gate coverage for preservation behavior.

## Linked Features

- [Feature 098 - Runtime Scope Round-Trip Preservation for Unknown Keys](/Users/tino/PhpstormProjects/forge/docs/features/098-runtime-scope-round-trip-preservation-for-unknown-keys.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
