# Explain Facet Regression Coverage Is Incomplete

## Problem

Current quality gates cover explain structured synthesis only, but not facet-specific behavior from features 047/058/059/060.

## Evidence

- `scripts/run_quality_gates.py` includes `gate_explain_structured_synthesis`.
- No dedicated gates for:
  - alias routing parity (`explain:<facet>` vs `explain --focus`)
  - `settings_influences`, `default_values`, `llm_participation`, `output_surfaces`
  - dependency/resource direction and source-scope edge contracts

## Required behavior

- Explain facet contracts must be regression-tested directly.
- Alias/flag parity and facet-specific sections must be validated.
- Negative tests (conflicts/invalid combos) must be covered.

## Done criteria

- New quality gates exercise all explain facets and key options (`--focus`, `--direction`, `--source-scope`).
- Gate failures clearly identify facet contract regressions.

## Linked Features

- [Feature 081 - Explain Facet Quality Gate Matrix](/Users/tino/PhpstormProjects/forge/docs/features/081-explain-facet-quality-gate-matrix.md)

## Implemented Behavior (Current)

- Explain facet behavior is now covered by a dedicated gate matrix (`gate_explain_facet_quality_matrix`).
- Coverage includes alias/flag parity, facet section presence, direction/source-scope contracts, and negative conflict handling.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_explain_facet_quality_matrix` passes.

## Known Limits / Notes

- The matrix validates contracts and parity; precision/semantic fixes for individual facets are handled in follow-up issues.
