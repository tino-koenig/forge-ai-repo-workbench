# Web Retrieval Foundation

## Description

This feature adds reusable web content retrieval for Forge, based on URL candidates from web search.

Primary goals:
- fetch and extract evidence from selected URLs
- provide normalized snippet payloads for downstream synthesis
- expose source and freshness metadata in a stable contract

## Spec

### Scope

Build on Feature 055 (web search candidates):
- consume `search.candidates[]` as retrieval input
- fetch bounded page content for top candidates
- extract snippets relevant to the user question
- expose retrieval output for consuming capabilities (for example ask modes)

### Preconditions and dependency

Dependency:
- Feature 055 must provide candidate URLs and host-policy-filtered search output.

Execution gate:
- retrieval is only attempted when search produced allowed candidates.

### Retrieval policy

Host policy:
- must inherit and enforce allowlist decisions from search stage
- must not fetch disallowed hosts even if candidates exist externally

Budget policy:
- `max_urls_fetched`
- `max_content_chars_per_url`
- `max_total_context_chars`
- `max_snippets`
- `max_retrieval_time_ms`

Safety:
- no hidden writes
- robust parser fallback for malformed pages
- explicit warning when extraction quality is low

### Retrieval pipeline

Deterministic staged pipeline:
1. pick top candidates from search output
2. fetch page content with bounded timeouts
3. normalize text extraction (HTML -> text blocks)
4. select relevance snippets against question terms
5. pass snippets to LLM answer synthesis
6. emit answer with citation list and uncertainty notes

### Output contract

Retrieval output must include metadata (mode-specific embedding allowed):
- `retrieval.used` (bool)
- `retrieval.fetched_count`
- `retrieval.extracted_snippet_count`
- `retrieval.sources[]` with:
  - `url`
  - `title`
  - `source_type` (`web_docs` | `web_general`)
  - `source_origin` (`web_search`)
  - `retrieved_at`
  - optional freshness fields (`published_at`, `updated_at`)
- optional `citations[]` array referencing source URLs/ids when downstream mode synthesizes answers

Text output requirements:
- concise retrieval summary
- visible fetched source list (or references)
- explicit uncertainty when extraction quality is low

### Freshness and latest alignment

For retrieved docs:
- include freshness caveat when publish/update metadata is unavailable
- prefer newer pages when multiple candidates provide comparable relevance

Alignment path:
- ask/research workflows can reuse retrieval primitives with mode-specific freshness policy.

### Failure and fallback

Fallback order:
1. retrieval from searched candidates
2. reduced retrieval budget from same candidates
3. search-only response with explicit warning
4. model-only response with explicit warning

Failure conditions to report explicitly:
- fetch timeout/network errors
- parser/extraction failures
- empty snippet set after fetch
- budget exhaustion

## Design

### Why this feature

Search alone is not enough for grounded web-based answers. Retrieval + snippet extraction is the minimum reusable base for auditable synthesis.

### Non-goals

- no full-site crawler beyond bounded candidate set
- no bypass of search-stage host policy
- no replacement of repository-grounded analysis modes

## Definition of Done

- retrieval consumes search candidates and fetches bounded web content
- output contract includes retrieval/source metadata
- fallback states are explicit and safe
- behavior remains debuggable with deterministic budget traces

## Implemented Behavior (Current)

- Added shared web-retrieval foundation module:
  - `core/web_retrieval_foundation.py`
  - retrieval policy builder (`build_web_retrieval_policy`)
  - bounded retrieval executor (`run_web_retrieval`)
- Retrieval behavior:
  - consumes host-allowlisted candidates from web search (Feature 055)
  - fetches bounded HTML content with timeout and time-budget guards
  - extracts normalized page text and relevance-ranked snippets
  - emits source metadata (`url`, `title`, `retrieved_at`, `snippet_count`)
- Ask integration:
  - `ask:docs` and `ask:latest` now run retrieval after search
  - ask contract emits `sections.ask.retrieval` with usage/policy/source/citation data
  - LLM evidence payload prefers retrieval snippets over search-title-only evidence

## How To Validate Quickly

- Full view:
  - `forge --view full ask:docs --profile typo3-v14 "TYPO3 routing docs"`
  - verify retrieval summary (`Web retrieval used`, `fetched`, `snippets`, `Retrieved sources`)
- JSON contract:
  - `forge --output-format json ask:docs --profile typo3-v14 "TYPO3 routing docs"`
  - inspect `sections.ask.retrieval.used`, `sources`, `citations`, and `fallback_reason`
- Fallback behavior:
  - run with blocked network and verify explicit retrieval warnings/fallback notes

## Known Limits / Notes

- Retrieval is intentionally bounded and snippet-oriented (no crawler/full-document indexing).
- Current extraction relies on robust HTML text normalization heuristics (no JS rendering).
- Freshness metadata beyond `retrieved_at` is not yet extracted in this phase.
