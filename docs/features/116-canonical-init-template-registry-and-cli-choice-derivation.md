# Canonical Init Template Registry and CLI Choice Derivation

## Description

Use one canonical init template/option registry and derive CLI parser choices from it.

## Addresses Issues

- [Issue 53 - Init Template and Option Choices Are Duplicated Across CLI and Mode](/Users/tino/PhpstormProjects/forge/docs/issues/53-init-template-and-option-choices-are-duplicated-across-cli-and-mode.md)

## Spec

- Extract canonical init template metadata to a shared foundation module.
- Derive CLI `--template` choices from canonical registry.
- Where applicable, derive related option domains from canonical constants.
- Preserve deterministic help output and command UX.

## Definition of Done

- No duplicated template-id literal lists remain between CLI and mode runtime.
- Template changes propagate automatically to parser validation/help.
- Regression test enforces parser/runtime registry consistency.

## Implemented Behavior (Current)

- Canonical init registry moved to [core/init_foundation.py](/Users/tino/PhpstormProjects/forge/core/init_foundation.py).
- CLI `forge init` choices (`--template`, `--output-language`, `--review-strictness`, `--index-enrichment`) now derive from shared init foundation constants.
- `modes/init.py` resolves templates from the same shared registry.

## How To Validate Quickly

- Run `forge init --help` and verify option choices are shown as expected.
- Run `python3 scripts/run_quality_gates.py` and confirm the init parser-choice drift gate passes.

## Known Limits / Notes

- This feature centralizes template/choice contracts; it does not change generated init file semantics by itself.
