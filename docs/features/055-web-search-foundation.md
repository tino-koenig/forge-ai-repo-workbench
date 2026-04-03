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
