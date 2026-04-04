# Query Substring Matching Causes False-Positive Retrieval

## Problem

Query retrieval currently matches terms via naive substring checks (`term in line`).
This causes high-noise hits for short/common fragments and can dominate ranking.

Observed example:
- question: `Wo ist enrich_detailed_context definiert?`
- planner lead term contains `enrich_detailed_context`, but search terms also include `ist`
- `ist` matches unrelated text fragments like `exists`, `list`, `dist`
- top result drifts to unrelated files (for example `core/session_store.py`)

## Evidence

- `modes/query.py`: content matching in `collect_matches` uses substring matching over full lines.
- Repro command:
  - `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Result shows unrelated evidence lines where term `ist` matched unrelated identifiers/text segments.

## Required behavior

- Retrieval matching must be token/identifier-aware instead of naive substring checks.
- Generic short terms must not outscore exact identifier evidence.
- Definition/location queries should not be derailed by stopword fragments.

## Done criteria

- Query matching no longer treats `ist` as match for `exists`/`list`/`dist`.
- Repro query above resolves `modes/query.py` as top hit.
- Regression gate covers token-aware matching for DE/EN natural-language questions.

## Linked Features

- [Feature 077 - Query Token-Aware Matching and Exact-Term Retrieval Contract](/Users/tino/PhpstormProjects/forge/docs/features/077-query-token-aware-matching-and-exact-term-retrieval-contract.md)

## Implemented Behavior (Current)

- Query content matching no longer uses naive substring checks for retrieval.
- Boundary-aware term matching is applied in repository and framework-local file scans.
- The `Wo ist enrich_detailed_context definiert?` repro now resolves to `modes/query.py` as top result under mock planner.

## How To Validate Quickly

- `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Check that:
  - top likely location is `modes/query.py`
  - no `content_match` evidence for term `ist` is caused by words like `exists`/`list`/`dist`

## Known Limits / Notes

- Non-content channels (for example graph text matching) still have independent matching behavior and are not part of this issue scope.
