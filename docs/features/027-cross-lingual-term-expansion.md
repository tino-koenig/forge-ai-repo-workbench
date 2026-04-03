# Cross-Lingual Term Expansion

## Description

This feature adds language-aware query term expansion so users can ask questions in one language and still retrieve relevant code in another language.

Primary initial case:
- German user queries against predominantly English repositories.

## Spec

### Scope

Enhance query preprocessing with controlled multilingual expansion:
- detect query language (initially lightweight heuristic)
- derive mapped terms in target repository language (initial: DE <-> EN)
- merge multilingual terms into retrieval term set

### Expansion model

For each query:
1. keep original terms
2. add mapped equivalents (bounded count)
3. mark mapped terms as inferred

Expansion sources:
- deterministic dictionary/mapping table (required baseline)
- optional LLM-assisted expansion (profile/policy controlled)

### Profiles

Initial behavior:
- simple: deterministic mapping only, small limit
- standard: deterministic + optional LLM expansion
- detailed: deterministic + preferred LLM expansion

### Output transparency

Query output should include:
- detected source language (best effort)
- applied cross-lingual mappings
- whether LLM was used for expansion
- uncertainty note when mapping confidence is low

JSON section additions:
- `cross_lingual.source_language`
- `cross_lingual.mapped_terms`
- `cross_lingual.expansion_mode` (`deterministic` / `llm` / `hybrid`)

### Safety constraints

- expansion must be bounded
- no fabricated files/symbols from expansion alone
- reranking cannot introduce files not found by deterministic retrieval stage

## Design

### Why this feature

Cross-language querying is a practical need and a clear capability improvement for real-world use.

### Non-goals

- no full multilingual NLP system
- no translation service dependency in this feature
- no automatic locale inference from user account metadata

## Definition of Done

- German queries produce relevant English-code retrieval improvements on fixture scenarios
- expansion metadata is explicit in output
- deterministic fallback works without LLM
- quality gates include DE->EN regression cases

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 027; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
