# Query Path And Symbol Signals

## Description

This feature improves query candidate retrieval by adding explicit path and symbol signals from the index to ranking.

Primary goals:
- make path hints (for example `controller`, `sitepackage`) first-class signals
- use indexed `top_level_symbols` for stronger code-target retrieval
- keep scoring robust against noisy short directory names such as `api`

## Spec

### Scope

Extend query ranking with:
- path-based retrieval/scoring from relative file path and path segments
- symbol-based retrieval/scoring from indexed `top_level_symbols`
- summary-based retrieval/scoring from indexed `explain_summary`
- existing `path_class` usage retained
- explicit retrieval-source marking per candidate/evidence (`content_match`, `path_match`, `symbol_match`, `summary_match`)
- explicit source-origin metadata (`source_type`: `repo` | `framework` | `external`) for source-aware ranking

### Path scoring semantics

Signals should be explicit and bounded:
- exact filename or stem match: strong boost
- exact path-segment match: medium boost
- long-token substring in full path: weak boost
- path-fragment terms containing separators (`/`, `.`, `_`, `-`): strong boost on match
- multi-word terms should also be tokenized and matched as bag-of-tokens; this bag signal stays weaker than explicit full-fragment matches

Guardrail:
- short/common terms (length <= 3, e.g. `api`) must only add a minimal score, even on segment match
- total path boost must be capped

### Symbol scoring semantics

Use `top_level_symbols` from index entries:
- exact symbol match: strong boost
- prefix symbol match: medium boost
- long-token symbol substring: weak boost
- total symbol boost must be capped

### Summary scoring semantics

Use index enrichment `explain_summary`:
- direct multi-word term overlap: medium boost
- tokenized overlap (bag-of-tokens): weak-to-medium boost
- short/common token overlap alone must stay weak
- total summary boost must be capped

### Constraints

- keep deterministic behavior and index-optional fallback
- no hidden writes in query mode
- preserve inspectable scoring logic in code
- default ranking should prefer `source_type=repo` over framework hits unless repo evidence is weak

## Design

### Why this feature

Path intent is often explicit in user questions, while content-only matching can miss or under-rank relevant candidates. Indexed symbols are similarly high-signal for function/class-focused questions.

### Non-goals

- no vector or embedding search in this feature
- no replacement of existing lexical evidence model
- no aggressive boosts for short/common directory names

## Definition of Done

- query ranking uses bounded path and symbol signals
- query ranking uses bounded summary signals from index enrichment metadata
- path retrieval is a first-class candidate channel (not only fallback)
- short common path tokens are prevented from dominating scores
- index fallback behavior remains unchanged
- retrieval output can show both match-source and origin-source (`retrieval_source` and `source_type`)

## Implementation Notes (2026-04-03)

Implemented in `modes/query.py` with deterministic scoring and metadata output:
- candidate model now includes `source_type`
- evidence payload now includes `retrieval_source`
- source-aware ranking prefers `repo` candidates over `framework`/`external` when repo evidence exists
- `source_type` is derived from index metadata when available, otherwise from bounded path heuristics
- full-view text output and JSON contract expose both `retrieval_sources` and `source_type`

## Implemented Behavior (Current)

- Query term handling now prioritizes symbol-like and code-variant terms ahead of generic lexical terms.
- Weak generic terms (for example `where`, `find`, `code`, `source`, `file`) are suppressed by default in planner-driven query search; `where` is retained only in SQL-like contexts.
- Evidence scoring now uses weighted term classes across retrieval channels (`content_match`, `path_match`, `symbol_match`, `summary_match`).
- Symbol exact/prefix scoring is substantially stronger, and explicit definition-signature lines receive additional deterministic boost during candidate scoring.
- For symbol-like terms, path/summary retrieval now uses strict full-term matching instead of bag-of-token expansion to avoid false positives from partial tokens (for example `context` from `enrich_detailed_context`).
- Base query ranking removed hardcoded intent-specific boosts/hints (`entrypoint`, `llm`, `api_call`) to keep core behavior neutral; specialization should be configuration-driven in later phases.
- Planner-driven query term derivation now uses planner output directly as term input (search terms + code variants), followed by deterministic filtering/prioritization.
- Planner-driven base retrieval now uses planner `search_terms` only. Planner `code_variants` remain visible in diagnostics but are excluded from base retrieval term injection.
- `derive_search_terms` no longer performs term-class branching; it preserves filtered term order and leaves priority decisions to deterministic scoring.
- Deterministic scoring now incorporates search-term position weights (earlier terms rank higher) and source-channel priority (index-derived signals higher, docs lower).

## How To Validate Quickly

- Run:
  - `forge --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Verify in output:
  - `sections.query_planner.search_terms` is anchored on symbol/definition terms and omits weak generic terms where possible.
  - `sections.likely_locations[0]` aligns better with symbol-bearing files for definition-style questions.
  - `sections.action_orchestration.iterations[]` shows read/search progression without relying on weak-generic-only evidence.

## Known Limits / Notes

- Ranking remains lexical/deterministic (no embedding search).
- Symbol confidence depends on index freshness and available `top_level_symbols`.
- Planner output quality still influences recall; deterministic weighting reduces but does not fully remove planner noise.
