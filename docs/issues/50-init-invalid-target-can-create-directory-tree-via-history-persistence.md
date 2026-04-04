# Init Invalid Target Can Create Directory Tree via History Persistence

## Problem

When init target path is invalid/missing, command returns failure but still creates target directories through run-history persistence.
This violates safety expectations and can leave unexpected artifacts.

## Evidence

Repro:
- run `forge --repo-root <missing-path> init --non-interactive --template balanced --output-format json`
- command exits with failure
- `<missing-path>/` gets created, including `<missing-path>/.forge/runs.jsonl`

The creation happens after capability returns, during global `append_run(...)` path.

## Required behavior

- Failed init on invalid target must not create target directories/files.
- Failure should remain purely diagnostic.

## Done criteria

- Missing target path remains missing after failed init.
- No `.forge` artifacts are created on invalid-target failure path.
- Regression test covers this exact scenario.

## Linked Features

- [Feature 113 - Strict Invalid-Target No-Write Contract for Init](/Users/tino/PhpstormProjects/forge/docs/features/113-strict-invalid-target-no-write-contract-for-init.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
