# Index-Aware Retrieval Scope Contract

## Description

This feature defines a single deterministic retrieval-scope contract between index producers and read-only consumers (especially `query`).

Goal:
- make index participation states actionable in retrieval,
- keep behavior explicit,
- avoid hidden path-class drift between indexing and query-time scanning.

## Spec

### Scope

Apply the contract to read-only capabilities that scan repository files (`query` first, then `describe`/`review`/`test` where applicable).

### Retrieval semantics

When index exists:
- `hard_ignore`: never scanned/read.
- `index_exclude`: excluded from default retrieval.
- `low_priority`/`normal`/`preferred`: eligible for default retrieval.

When index is missing:
- fallback behavior remains available via repo scan.

### Explicit overrides

Add explicit source-scope toggles (or equivalent deterministic controls) to include `index_exclude` paths when needed.

### Transparency

Output should expose effective retrieval scope in machine-readable sections (for example source caps/scope metadata).

## Design

### Why this feature

Today indexing and retrieval can diverge in practice. A shared scope contract removes ambiguity and reduces noisy candidates.

### Non-goals

- no hidden auto-expansion into excluded paths
- no index mandatory requirement

## Definition of Done

- Query default retrieval honors index participation state when index is present.
- Explicit override path exists for including `index_exclude` sources.
- Regression fixture covers high-noise `vendor` scenario.
- JSON/full outputs expose the effective scope decision.

## Implemented Behavior (Current)

- Query content retrieval now enforces index participation by default when `.forge/index.json` exists.
- Paths classified as `index_exclude` or `hard_ignore` are excluded from default content scanning.
- Query output now exposes effective scope decisions in `sections.retrieval_scope`.
- Runtime override is available through `query.source_policy.source_scope_default = "all"` in repo/local config.

## How To Validate Quickly

- Ensure index exists:
  - `python3 forge.py index`
- Run:
  - `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Verify:
  - `sections.retrieval_scope.index_participation_enforced == true` (default)
  - high-noise `vendor/` paths do not dominate top likely locations
- Gate check:
  - `PYTHONPATH=. python3 -c "import shutil,tempfile; from pathlib import Path; from scripts.run_quality_gates import FIXTURE_BASIC_SRC, gate_query_index_scope_and_symbol_first; td=tempfile.TemporaryDirectory(prefix='forge-gate-'); repo=Path(td.name)/'repo'; shutil.copytree(FIXTURE_BASIC_SRC, repo); gate_query_index_scope_and_symbol_first(repo); print('ok')"`

## Known Limits / Notes

- Scope enforcement in this feature targets default content retrieval; auxiliary channels can still contribute separate evidence.
