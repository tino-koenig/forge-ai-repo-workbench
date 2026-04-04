# Ask Latest Freshness Policy

## Description

Introduce a distinct freshness-oriented behavior for `ask:latest` beyond docs preset defaults.

Goals:
- make `ask:latest` meaningfully different from `ask:docs`,
- improve freshness confidence for time-sensitive web answers,
- surface freshness signals explicitly.

## Spec

### Freshness strategy

- recency-aware query variants for latest mode
- source ranking preferences that consider freshness metadata when available
- explicit freshness caveats when metadata is missing

### Contract additions

Expose freshness metadata, e.g.:
- freshness policy mode
- recency query variants used
- per-source freshness signals (published/updated/retrieved)
- freshness confidence note

## Definition of Done

- `ask:latest` executes a freshness-specific policy distinct from docs mode.
- Output contract contains freshness strategy/signals.
- Tests validate mode divergence and fallback behavior when freshness metadata is absent.

## Addresses Issues

- [16-ask-latest-has-no-distinct-freshness-behavior.md](/Users/tino/PhpstormProjects/forge/docs/issues/16-ask-latest-has-no-distinct-freshness-behavior.md)

## Implemented Behavior (Current)

- Web search policy now supports explicit `freshness_mode` (`docs` or `latest`).
- `ask:latest` uses dedicated recency query variants and distinct search-policy limits from `ask:docs`.
- Ask contract now includes `sections.ask.freshness` with strategy and signal metadata.

## How To Use

- Use:
  - `forge ask:latest "..."`
- In JSON output, inspect:
  - `sections.ask.search.policy.freshness_mode`
  - `sections.ask.search.query_plan`
  - `sections.ask.freshness`

## Known Limits / Notes

- Freshness confidence is conservative when only retrieval timestamps are available and no published/updated source metadata can be extracted.
