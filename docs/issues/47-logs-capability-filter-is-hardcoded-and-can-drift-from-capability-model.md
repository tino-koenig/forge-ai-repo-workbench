# Logs Capability Filter Is Hardcoded and Can Drift from Capability Model

## Problem

`forge logs --capability` uses a hardcoded choice list in CLI parsing.
This can drift when capabilities evolve, causing valid capabilities to be rejected or stale values to remain accepted.

## Evidence

- `forge_cmd/cli.py` defines explicit choices tuple for `--capability`.
- Capability names are already centrally defined in `core/capability_model.py`.
- The two lists are maintained separately, creating contract drift risk.

## Required behavior

- `logs --capability` choices should be derived from the canonical capability model (single source of truth).
- Parser/help output should remain deterministic and explicit.

## Done criteria

- CLI `--capability` choices are generated from the central capability model.
- Regression test fails if capability-model additions are not reflected in logs filtering.

## Linked Features

- [Feature 109 - Derive Logs Capability Filter Choices from Capability Model](/Users/tino/PhpstormProjects/forge/docs/features/109-derive-logs-capability-filter-choices-from-capability-model.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
