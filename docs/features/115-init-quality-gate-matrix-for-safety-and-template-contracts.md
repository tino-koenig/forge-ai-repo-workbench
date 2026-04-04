# Init Quality-Gate Matrix for Safety and Template Contracts

## Description

Add dedicated init regression gates to enforce onboarding and safety contracts.

## Addresses Issues

- [Issue 52 - Init Regression Coverage Is Missing for Safety and Template Contracts](/Users/tino/PhpstormProjects/forge/docs/issues/52-init-regression-coverage-is-missing-for-safety-and-template-contracts.md)

## Spec

- Add init-focused gates covering:
  - list-templates is non-mutating
  - dry-run is non-mutating
  - invalid-target failure is non-mutating
  - non-tty interactive behavior
  - overwrite-blocking and `--force`
  - template output contract (`config.toml`, `review-rules.toml`, `template-meta.toml`, local example)
  - `init -> doctor` coherence baseline
- Keep gate failures specific and actionable.

## Definition of Done

- Init gates run in standard quality-gate pipeline.
- Gate matrix catches side-effect regressions and template drift.
- CI/local gate output pinpoints contract breaches.

## Implemented Behavior (Current)

- Init coverage is now part of the standard quality-gate pipeline with dedicated gates for:
  - non-mutating flows (`--list-templates`, `--dry-run`, non-tty failure, invalid target)
  - overwrite safety (`overwrite_blocked` without `--force`, deterministic write with `--force`)
  - template output contracts across all templates
  - `init -> doctor` baseline coherence
  - source-policy onboarding persistence

## How To Validate Quickly

- Run `python3 scripts/run_quality_gates.py`.
- Confirm init-specific gates pass:
  - `gate_init_non_mutating_flows`
  - `gate_init_invalid_target_no_write`
  - `gate_init_overwrite_block_and_force_contract`
  - `gate_init_template_output_contract_matrix`
  - `gate_init_doctor_provider_baseline_coherence`

## Known Limits / Notes

- Gates assert deterministic file/contract behavior; they do not validate visual/UX wording of interactive prompts.
