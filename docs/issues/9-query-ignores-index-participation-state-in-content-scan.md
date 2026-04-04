# Query Ignores Index Participation State in Content Scan

## Problem

`forge query` scans repository file content via `iter_repo_files(...)` and then ranks matches even when a path is marked `index_exclude` in the index.

Observed behavior:
- `modes/index.py` classifies `vendor/` as `index_exclude`.
- `modes/query.py` content retrieval still scans all repo files returned by `core/repo_io.py::iter_repo_files`.
- Paths not present in index default to `path_class="normal"` in ranking.
- In practice, `vendor/*` content can appear in top results for code-location questions although it is excluded from index participation.

This breaks the intended separation between index participation and default relevance behavior and causes noisy ranking.

## Required behavior

- When index data is available, default query content scanning should honor index participation:
  - `hard_ignore` and `index_exclude` should not be treated as normal default candidates.
- Inclusion of `index_exclude` paths should be explicit (for example via future flag or explicit source scope).
- Ranking should not silently up-classify non-indexed paths to `normal` when index metadata is present.

## Done criteria

- Query retrieval defaults align with index participation semantics when `.forge/index.json` exists.
- `vendor/` noise does not appear in default top results in a regression fixture where `vendor` contains high lexical overlap.
- A quality gate covers this behavior.

## Linked Features

- [Feature 067 - Index-Aware Retrieval Scope Contract](/Users/tino/PhpstormProjects/forge/docs/features/067-index-aware-retrieval-scope-contract.md)
- [Feature 068 - Query Deterministic Symbol-First Resolution](/Users/tino/PhpstormProjects/forge/docs/features/068-query-deterministic-symbol-first-resolution.md)

## Implemented Behavior (Current)

- Query content scanning now honors index participation classes by default when index data is present.
- Non-participating paths (`index_exclude`, `hard_ignore`) are excluded from default content retrieval unless explicitly widened via source policy.
- Deterministic symbol-first resolution was added for definition queries so indexed exact symbols dominate generic lexical noise.

## How To Validate Quickly

- `python3 forge.py index`
- `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Check:
  - `sections.retrieval_scope.index_participation_enforced == true`
  - `sections.symbol_resolution.exact_hits >= 1`
  - top result is the defining source file, not high-noise `vendor/` paths

## Known Limits / Notes

- Scope enforcement is default behavior; deliberate widening requires explicit source-policy configuration.
