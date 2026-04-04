# Describe Important-File Ranking Scope Policy

## Description

Constrain repository-level important-file ranking to prefer primary project scope and reduce fixture/example noise.

## Addresses Issues

- [Issue 37 - Describe Important-File Selection Can Surface Irrelevant Fixture Paths](/Users/tino/PhpstormProjects/forge/docs/issues/37-describe-important-file-selection-can-surface-irrelevant-fixture-paths.md)

## Spec

- Add deterministic scope-aware ranking signals (root proximity, index participation/path class, repository area role).
- Deprioritize fixture/example/test subtree candidates for repo-overview next-step selection.
- Emit rationale metadata for selected important files.

## Definition of Done

- Important-file output favors primary repo entry/config paths in fixture-heavy repos.
- Next-step suggestions are less noisy and more actionable.
- Regression tests cover fixture-dense repositories.

## Implemented Behavior (Current)

- Describe repository-level important-file selection now uses deterministic ranking with scope-aware policy:
  - root/near-root proximity
  - primary project area hints (`src/`, `core/`, `modes/`, `cmd/`)
  - conventional entry/config filenames
  - explicit fixture/test/example subtree de-prioritization
- Describe now emits rationale metadata in `sections.important_file_rationale` with per-path score and rationale tags.
- `sections.important_files` and next-step suggestions now prefer primary repository scope over nested fixture trees by default.
- Added regression gate `gate_describe_important_file_scope_policy`.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_describe_important_file_scope_policy` passes.

## Known Limits / Notes

- Ranking is deterministic and lexical/scope-based; it intentionally avoids hidden model-dependent reordering.
