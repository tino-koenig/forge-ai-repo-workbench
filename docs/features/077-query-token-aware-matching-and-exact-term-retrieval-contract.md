# Query Token-Aware Matching and Exact-Term Retrieval Contract

## Description

Improve query retrieval precision by replacing substring-based matching with token/identifier-aware matching.

Goals:
- eliminate false positives from short generic fragments
- preserve deterministic behavior
- keep symbol/identifier anchors dominant for locate-definition intents

## Addresses Issues

- [Issue 20 - Query Substring Matching Causes False-Positive Retrieval](/Users/tino/PhpstormProjects/forge/docs/issues/20-query-substring-matching-causes-false-positive-retrieval.md)

## Spec

### Matching contract

- Content matching must use token-aware logic (word/identifier boundaries), not unconstrained substring checks.
- Identifier-like terms (snake_case, camelCase, dotted names) should be matched exactly or via bounded structural decomposition.
- Generic short terms should not match inside unrelated identifiers by default.

### Ranking contract

- Exact identifier hits in code/symbol channels must outrank incidental generic token hits.
- Evidence should reflect match type explicitly (for example `identifier_exact`, `identifier_token`, `symbol_exact`).

### Compatibility

- Existing output contract remains stable; only evidence quality and ranking improve.

## Definition of Done

- Query no longer matches `ist` against `exists`/`list`/`dist` in content channel.
- Definition query for `enrich_detailed_context` resolves to `modes/query.py` in top result under mock planner.
- Regression gates cover DE and EN locate-definition phrasings.

## Implemented Behavior (Current)

- Query content retrieval now applies boundary-aware term matching instead of unconstrained substring matching.
- Repository and framework-local content scans both use the same token-aware matcher.
- New quality gate `gate_query_token_aware_matching` verifies that exact identifier evidence wins for definition queries and that `ist` does not match inside unrelated identifiers in `content_match`.

## How To Validate Quickly

- Run:
  - `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Verify:
  - top likely location is `modes/query.py`
  - content evidence for term `ist` does not come from fragments like `exists` or `list`
- Gate check:
  - `PYTHONPATH=. python3 -c "import shutil,tempfile; from pathlib import Path; from scripts.run_quality_gates import FIXTURE_BASIC_SRC, gate_query_token_aware_matching; td=tempfile.TemporaryDirectory(prefix='forge-gate-'); repo=Path(td.name)/'repo'; shutil.copytree(FIXTURE_BASIC_SRC, repo); gate_query_token_aware_matching(repo); print('ok')"`

## Known Limits / Notes

- Token-aware enforcement is currently applied to content channels (`content_match`), not all auxiliary channels (for example graph edge text blobs).
