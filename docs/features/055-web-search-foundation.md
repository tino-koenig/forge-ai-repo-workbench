# Web Search Foundation

## Description

This feature introduces a reusable web-search foundation for Forge capabilities.

Primary goals:
- provide a shared URL discovery layer for multiple modes
- enforce explicit host policy and bounded search budgets
- return deterministic, inspectable URL candidate sets for downstream retrieval/synthesis

## Spec

### Scope

Add capability-agnostic search primitives:
- normalized web query generation
- policy-constrained result discovery
- ranked candidate URL output for downstream consumers

Search behavior:
- discover candidate pages via web search
- rank and filter URLs under source policy
- expose selected candidates in a stable contract section usable by other features

### Source policy

Primary source controls:
- profile-driven allowlist from `.forge/frameworks.toml` (`profiles.docs.allowlist_hosts`)
- profile-driven entrypoints (`profiles.docs.entrypoints`) as search seeds
- optional fallback allowlist when no profile is selected

Hard requirements:
- deny disallowed hosts according to active search policy
- no hidden writes
- explicit warning when search scope is downgraded or blocked by source policy

### Search pipeline

Deterministic staged pipeline:
1. normalize question + detect documentation intent
2. generate bounded search queries (entrypoint-aware)
3. execute web search with host allowlist enforcement
4. normalize and deduplicate URLs
5. produce ranked candidate URL set with provenance metadata

Suggested limits (configurable):
- `max_queries`
- `max_urls_considered`
- `max_urls_returned`
- `max_search_time_ms`

### Output contract

Search output must include structured metadata (mode-specific embedding allowed):
- `search.used` (bool)
- `search.policy` (allowlist decision summary)
- `search.candidates[]` with:
  - `url`
  - `host`
  - optional `title_hint`
  - `source_type` (`web_docs`)
  - `source_origin` (`web_search`)
  - `rank`
  - `discovery_query`

Text output requirements:
- concise search summary
- visible top candidate URLs
- explicit uncertainty when no allowed candidates are found

### Separation from retrieval

This feature explicitly does not fetch page content.
Page fetching/extraction is handled by a separate retrieval feature.

### Failure and fallback

Fallback order:
1. profile-restricted search
2. reduced search within safe global allowlist
3. no-search fallback with explicit warning and `search.used = false`

Failure conditions to report explicitly:
- no allowed results
- search provider/network errors
- policy filter drops all candidates
- budget/time exhaustion

## Design

### Why this feature

Forge needs a deterministic URL discovery phase before retrieval. Separating search from retrieval improves inspectability, fallback clarity, and staged rollout control.

### Non-goals

- no generic unconstrained web browsing for all ask presets
- no content fetching/parsing in this feature
- no silent host-policy bypass
- no replacement of repository-local analysis capabilities

## Definition of Done

- web search executes in bounded form under explicit host policy
- output contract exposes search candidates and policy/fallback status
- no content retrieval side effects are introduced
- failure and downgrade paths are explicit and safe

## Implemented Behavior (Current)

- Added shared web-search foundation module:
  - `core/web_search_foundation.py`
  - policy builder (`build_web_search_policy`)
  - bounded search executor (`run_web_search`)
  - normalized candidate/output dataclasses
- Host policy behavior:
  - consumes `profiles.docs.allowlist_hosts` and `profiles.docs.entrypoints` from framework profiles
  - enforces allowlist filtering for discovered URLs
  - supports fallback docs allowlist when profile data is missing/incomplete
- Search execution behavior:
  - query plan generation with `site:<host>` constrained variants
  - bounded candidate collection and deduplication
  - provider fallback visibility (`fallback_reason`, warnings, `used=false`)
- Foundation integration:
  - `ask:docs` and `ask:latest` now consume the web-search foundation
  - search metadata is emitted in `sections.ask.search` (used/policy/query_plan/candidates)
  - no web content retrieval is performed in this feature phase

## How To Validate Quickly

- Docs search preset:
  - `forge --view full ask:docs --profile typo3-v14 "TYPO3 routing docs"`
  - verify `Web search used`, `Allowed hosts`, and candidate URLs in full view
- JSON contract:
  - `forge --output-format json ask:docs --profile typo3-v14 "TYPO3 routing docs"`
  - inspect `sections.ask.search`
- Fallback visibility:
  - run with missing/unconfigured profile and inspect warnings/fallback reason in `uncertainty` and `sections.ask.search`

## Known Limits / Notes

- Current provider implementation uses bounded DuckDuckGo HTML search and can fail due to network/provider restrictions.
- Search quality depends on host allowlist and query phrasing; retrieval/synthesis quality is handled by separate feature 056.
- This feature intentionally does not fetch page bodies or produce citation-grounded synthesis.
