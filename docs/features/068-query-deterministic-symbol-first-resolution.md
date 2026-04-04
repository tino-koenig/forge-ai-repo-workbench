# Query Deterministic Symbol-First Resolution

## Description

This feature adds a deterministic symbol-first resolution step for locate-definition questions before broad lexical ranking.

Goal:
- return precise file/location answers when symbol evidence already exists,
- reduce dependence on generic lexical terms,
- keep behavior transparent and auditable.

## Spec

### Trigger

For queries whose intent is definition/location of code entities (function/class/variable), run a symbol-first stage.

### Resolution strategy

- Use exact and normalized symbol candidates from index metadata first.
- If exact symbol matches exist, prioritize those candidates ahead of generic lexical matches.
- Attach explicit evidence type (`symbol_exact`, `symbol_prefix`, etc.) and confidence.

### Fallback

If symbol stage has no usable evidence, continue with existing lexical/path/summary/graph ranking.

## Design

### Why this feature

A symbol already present in `.forge/index.json` should dominate generic terms like `function`/`definition`.

### Non-goals

- no opaque LLM-only resolution
- no mandatory AST pipeline

## Definition of Done

- Definition queries with exact indexed symbol resolve to the defining file in top results.
- Output shows symbol-stage evidence explicitly.
- Regression test covers `enrich_detailed_context`-style query and prevents fallback to filler-term dominance.

## Implemented Behavior (Current)

- Query now triggers a deterministic symbol-first stage for definition/location-oriented questions.
- Anchor terms (primarily planner lead terms) are resolved against indexed symbols before broad lexical ranking.
- Exact symbol hits are emitted as explicit evidence (`symbol_exact`) and receive dominant deterministic weighting.
- Query output now exposes symbol-stage metadata in `sections.symbol_resolution`.

## How To Validate Quickly

- Run:
  - `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Verify:
  - top likely location resolves to the defining file
  - `sections.symbol_resolution.triggered == true`
  - `sections.symbol_resolution.exact_hits >= 1`
  - evidence includes `symbol_exact: ...` when indexed exact symbol is available

## Known Limits / Notes

- Symbol-first currently depends on available index symbol metadata (`top_level_symbols`) and does not include AST-level semantic resolution.
