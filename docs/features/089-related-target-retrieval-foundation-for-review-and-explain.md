# Related-Target Retrieval Foundation for Review and Explain

## Description

Create a shared deterministic related-target retrieval foundation for modes that expand context (review/explain).

## Addresses Issues

- [Issue 32 - Related-File Selection for Review Is Too Lexical and Can Add Noise](/Users/tino/PhpstormProjects/forge/docs/issues/32-related-file-selection-for-review-is-too-lexical-and-can-add-noise.md)

## Spec

- Introduce weighted related-target scoring using signals such as:
  - import/dependency links
  - directory locality
  - index metadata/path class
  - lexical fallback
- Expose rationale metadata for chosen related targets.

## Definition of Done

- Review and explain use shared related-target retrieval primitives.
- Noise from lexical collisions is reduced in fixtures.
- Output includes relation rationale for selected related targets.

## Implemented Behavior (Current)

- Added shared deterministic related-target ranking foundation in `core.analysis_primitives.rank_related_targets`.
- Ranking now combines weighted signals:
  - directory locality
  - import-token linkage
  - index/path-class weighting
  - lexical stem fallback
- Review now uses ranked related targets and emits rationale metadata in `sections.related_targets`.
- Explain now uses the same ranked foundation and emits rationale metadata in `sections.related_target_rationale`.
- Added regression gate `gate_related_target_retrieval_foundation`.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_related_target_retrieval_foundation` passes.

## Known Limits / Notes

- Signal extraction is intentionally lightweight and static (no runtime dependency graph resolution); deterministic weighting remains transparent and extensible.
