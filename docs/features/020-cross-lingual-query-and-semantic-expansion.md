# Cross-Lingual Query and Semantic Expansion

## Description

This feature improves `forge query` quality by combining deterministic retrieval with controlled LLM-assisted semantic expansion and reranking.

Primary user value:
- questions in German against English codebases
- better results for conceptual questions that do not match literal symbols

## Spec

### Scope

Enhance query pipeline with two explicit optional steps:
1. query semantic expansion
2. evidence-aware candidate reranking

Deterministic evidence collection remains mandatory.

### Query expansion

From the user question, derive:
- normalized core intent
- multilingual term variants (initial: German <-> English)
- symbol-style hypotheses (snake_case, camelCase, common prefixes)

Constraints:
- expansions must be bounded (max generated terms per profile)
- generated terms must be included in metadata
- fallback to deterministic lexical terms when LLM unavailable

### Reranking

Given deterministic candidate set and evidence snippets:
- apply optional LLM rerank for top-N candidates
- produce score justification per promoted candidate

Constraints:
- rerank cannot introduce files that were not retrieved deterministically
- rerank metadata must show pre/post rank movement

### Profiles

Initial profile behavior:
- simple: no LLM expansion/rerank
- standard: optional expansion + optional rerank
- detailed: preferred expansion + optional rerank

### Output changes

Add query JSON sections:
- `semantic_expansion`
- `retrieval_stage`
- `rerank_stage`
- `cross_lingual` (source language guess + applied mappings)

Text output should include concise summary of:
- whether expansion was applied
- whether reranking changed top results

### Safety and transparency

- evidence remains repository-grounded
- all inferred terms are marked as inference
- uncertainty notes include language-mapping limitations
- no write effects introduced

## Design

### Why this feature

Current query quality is mainly lexical.
Users expect intent-level matching and cross-language querying in real repositories.

### Non-goals

- no vector database in this feature
- no full multilingual NLP stack
- no implicit autonomous follow-up actions

## Definition of Done

- German query can successfully retrieve relevant locations in English fixture repo
- expansion and rerank are explicit, bounded, and fallback-safe
- output clearly distinguishes retrieval evidence vs semantic inference
- quality gates include:
  - no-LLM deterministic baseline
  - LLM expansion/rerank path
  - cross-lingual regression scenario

## Implemented Behavior (Current)

- This feature is superseded as a standalone rollout and is now covered by split implementation tracks:
  - cross-lingual term expansion in Feature 027
  - planner-driven multilingual normalization/term shaping in Feature 028
  - output-language control in Feature 035
- Query output continues to expose cross-lingual metadata (`sections.cross_lingual`) and planner normalization signals.

## How To Validate Quickly

1. Run a German query against an English-code fixture:
   - `forge --output-format json query "Wo ist die Funktion X definiert?"`
2. Verify output contains:
   - `sections.cross_lingual.source_language`
   - `sections.cross_lingual.mapped_terms`
   - `sections.query_planner.normalized_question_en`
3. Verify output-language behavior via:
   - `--llm-output-language de|en|auto`

## Known Limits / Notes

- Feature 020 should not be extended independently anymore.
- New work should target the active split contracts (027/028/035) and keep behavior explicit in those specs.
