# `ask:latest` Has No Distinct Freshness Behavior

## Problem

`ask:latest` currently runs the same search/retrieval policy and query-plan strategy as `ask:docs`.

Observed behavior:
- Same web mode (`docs_web_search`), same policy limits, same host-constrained plan shape.
- No recency-aware query strategy, no freshness scoring, no additional freshness metadata extraction.

This does not satisfy the promised freshness-focused intent of `ask:latest`.

## Required behavior

- `ask:latest` must apply explicit freshness strategy beyond docs preset defaults.
- Runtime output must indicate freshness policy and caveats clearly.

## Done criteria

- `ask:latest` uses distinct recency/freshness controls compared to `ask:docs`.
- Contract sections expose freshness strategy + resulting signals.
- Regression tests validate divergence from docs preset behavior.

## Linked Features

- [073-ask-latest-freshness-policy.md](/Users/tino/PhpstormProjects/forge/docs/features/073-ask-latest-freshness-policy.md)

## Implemented Behavior (Current)

- `ask:latest` now runs with a dedicated freshness policy distinct from `ask:docs`.
- Search policy now carries `freshness_mode` and latest-mode query planning includes recency variants.
- Ask output exposes freshness strategy/signals in `sections.ask.freshness`:
  - `mode`
  - `recency_query_variants`
  - per-source freshness signals (`retrieved_at`, with caveats when publish/update metadata is missing)
  - `confidence_note`

## How To Validate Quickly

- Run with web access enabled:
  - `FORGE_RUNTIME_SESSION_JSON='{"access.web":true}' python3 forge.py --output-format json --llm-provider mock ask:docs "typo3 release notes"`
  - `FORGE_RUNTIME_SESSION_JSON='{"access.web":true}' python3 forge.py --output-format json --llm-provider mock ask:latest "typo3 release notes"`
- Verify:
  - `ask:latest` has `sections.ask.freshness.mode == "latest"`
  - `ask:latest` includes non-empty `recency_query_variants`
  - `ask:latest` query plan differs from `ask:docs`

## Known Limits / Notes

- Freshness currently relies on deterministic recency query variants plus retrieval timestamp; source-native published/updated metadata extraction is not yet implemented.
