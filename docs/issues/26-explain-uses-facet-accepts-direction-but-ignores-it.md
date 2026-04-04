# Explain Uses Facet Accepts Direction But Ignores It

## Problem

`explain:uses` accepts `--direction` and reports it in metadata, but behavior remains inbound-only regardless of provided direction.

## Evidence

- `modes/explain.py` builds `uses` answer from inbound edges only.
- Running `explain:uses ... --direction out` and `--direction in` produces identical inbound results.
- `sections.explain.direction` still echoes user input, creating a misleading contract.

## Required behavior

- Direction semantics must be explicit and consistent:
  - either enforce `uses => direction=in` (normalize/reject `out`),
  - or implement true bidirectional semantics.

## Done criteria

- CLI/contract behavior for `uses` + `--direction` is deterministic and non-misleading.
- Regression tests cover valid and invalid direction combinations.

## Linked Features

- [Feature 083 - Explain Facet Semantics and Argument Validation Contract](/Users/tino/PhpstormProjects/forge/docs/features/083-explain-facet-semantics-and-argument-validation-contract.md)

## Implemented Behavior (Current)

- `uses` direction behavior is now explicit:
  - requested `out` is normalized to effective `in`,
  - metadata reports requested vs effective values,
  - uncertainty notes include a normalization hint.
- Regression coverage ensures this contract remains deterministic.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_explain_facet_semantics_validation` passes.

## Known Limits / Notes

- The implementation currently enforces `uses => in` semantics; bidirectional `uses` behavior is intentionally out of scope.
