# Feature 002 Config Contract Diverges from Runtime Behavior

## Problem

Feature 002 specifies repo-owned functional config via:
- `.forge/defaults.yml`
- `.forge/repo.yml`

and a merge order that includes both files.

Current runtime behavior in index implementation uses hardcoded defaults plus `.forge/config.toml` enrichment settings. The documented `.forge/defaults.yml`/`.forge/repo.yml` contract is not implemented.

This creates a contract mismatch between implemented behavior and feature documentation/status.

## Required behavior

Choose one explicit direction and make docs + implementation consistent:
- either implement the specified yaml-based merge model,
- or update feature specs/status notes to reflect toml-based and hardcoded behavior.

## Done criteria

- No contradiction remains between Feature 002 spec and runtime config behavior.
- Validation docs show the canonical config sources for index path classes and enrichment settings.
- A regression/documentation check protects the chosen contract.

## Linked Features

- [Feature 105 - Index Config Contract Harmonization](/Users/tino/PhpstormProjects/forge/docs/features/105-index-config-contract-harmonization.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
