# Init Template and Option Choices Are Duplicated Across CLI and Mode

## Problem

Init template/option choices are defined in multiple places (CLI parser choices and mode-local template registry), creating drift risk.

## Evidence

- CLI hardcodes `--template` choices in `forge_cmd/cli.py`.
- Mode defines canonical `TEMPLATES` in `modes/init.py`.
- Similar duplication exists for related enum-like option domains.

## Required behavior

- Use one canonical source for init template ids/options and derive parser choices from it.
- Keep help output deterministic while removing duplicated literals.

## Done criteria

- CLI init choices are derived from canonical init template/option registry.
- Adding/removing template ids updates parser choices automatically.
- Regression test catches parser/template drift.

## Linked Features

- [Feature 116 - Canonical Init Template Registry and CLI Choice Derivation](/Users/tino/PhpstormProjects/forge/docs/features/116-canonical-init-template-registry-and-cli-choice-derivation.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
