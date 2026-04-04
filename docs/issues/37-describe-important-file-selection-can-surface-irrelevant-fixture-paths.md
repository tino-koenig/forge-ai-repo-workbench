# Describe Important-File Selection Can Surface Irrelevant Fixture Paths

## Problem

Repository-level describe may select "important files" from nested fixture/example trees, producing weak next-step guidance for the primary repository.

## Evidence

- `find_important_files` scans all discovered files and accepts generic names (`README.md`, `package.json`, `main.py`) regardless of repository area intent.
- Code path: `/Users/tino/PhpstormProjects/forge/modes/describe.py` (`find_important_files`).
- Repro in forge repo:
  - `python3 forge.py --llm-provider mock --output-format json --view full describe src/does_not_exist.py`
  - `sections.important_files` includes fixture paths under `tests/fixtures/...` as top candidates.

## Required behavior

- Important-file ranking for repo overview should prioritize root/primary project scope over nested fixture content.
- Selection rationale should be deterministic and auditable.

## Done criteria

- Fixture/test subtree paths are deprioritized by default for repo-overview important files.
- Next-step suggestions prefer primary repo entrypoints/config.
- Regression tests cover noisy fixture-heavy repositories.

## Linked Features

- [Feature 094 - Describe Important-File Ranking Scope Policy](/Users/tino/PhpstormProjects/forge/docs/features/094-describe-important-file-ranking-scope-policy.md)

## Implemented Behavior (Current)

- Describe important-file ranking now uses explicit scope-aware deterministic signals and de-prioritizes fixture/test/example subtree paths.
- Repository-level `important_files` and next-step hints now favor primary repo entry/config candidates.
- Describe now exposes auditable ranking rationale in `sections.important_file_rationale`.
- Regression coverage added via `gate_describe_important_file_scope_policy`.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_describe_important_file_scope_policy` passes.

## Known Limits / Notes

- Scope policy is deterministic and conservative; it does not rely on hidden learned weighting.
