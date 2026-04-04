# Index Config Contract Harmonization

## Description

Harmonize documented index configuration contract with actual runtime behavior.

## Addresses Issues

- [Issue 11 - Feature 002 Config Contract Diverges from Runtime Behavior](/Users/tino/PhpstormProjects/forge/docs/issues/11-feature-002-config-contract-diverges-from-runtime-behavior.md)

## Spec

- Choose one canonical direction:
  - implement documented `.forge/defaults.yml`/`.forge/repo.yml` merge model, or
  - update feature specs/docs to the implemented TOML-based contract.
- Ensure doctor/docs/status explicitly reflect the chosen contract.

## Definition of Done

- No contradiction between feature docs and runtime behavior remains.
- Config source model is clearly documented and validated.
- Regression/documentation checks prevent drift.

## Implemented Behavior (Current)

- Canonical direction chosen: docs were harmonized to the implemented TOML-based runtime contract.
- Index config model now documents `.forge/config.toml` + optional `.forge/config.local.toml` override instead of non-implemented `.forge/defaults.yml`/`.forge/repo.yml`.
- Feature 002 now reflects actual index runtime behavior and precedence.

## How To Validate Quickly

- Open [docs/features/002-index.md](/Users/tino/PhpstormProjects/forge/docs/features/002-index.md) and verify config sections reference TOML files only.
- Run `python3 scripts/run_quality_gates.py` and confirm the docs contract gate passes.

## Known Limits / Notes

- This feature harmonizes contract/docs; it does not introduce new index settings beyond the current `[index.enrichment]` scope.
