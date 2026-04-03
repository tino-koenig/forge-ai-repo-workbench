# LLM Cost and Token Tracking

## Description

This feature adds explicit per-request token and cost tracking for LLM usage.

It is intentionally separate from query-planning quality features.
Goal: observability and spend control without changing capability semantics.

## Spec

### Scope

Capture and expose LLM usage metrics for all LLM-assisted capabilities:
- query
- explain
- review
- describe
- test

Metrics per request:
- provider/model
- prompt/input tokens
- completion/output tokens
- total tokens
- estimated cost (if pricing configured)
- LLM latency
- fallback status

### Output exposure

Expose metrics in:
- JSON output (`sections.llm_usage.cost` and related fields)
- run history metadata for later analysis

Text output policy:
- no cost block in compact/standard by default
- available in full details mode

### Configuration

Add pricing configuration to `.forge/config.toml`:
- `llm.pricing.input_per_1k`
- `llm.pricing.output_per_1k`
- `llm.pricing.currency`

Controls:
- `llm.cost_tracking.enabled` (`true|false`)
- optional warning thresholds:
  - `llm.cost_tracking.warn_cost_per_request`
  - `llm.cost_tracking.warn_tokens_per_request`

### Behavior

- if provider returns usage tokens, use provider numbers
- if unavailable, set fields to `unknown` (do not fabricate)
- estimated cost only when pricing is configured and token counts are known

### Safety and constraints

- never log API keys or auth headers
- no behavior change in retrieval/review logic due to cost tracking alone
- missing pricing config must not fail capability execution

## Design

### Why this feature

Cost transparency is necessary for production usage and model strategy decisions.
Separating this from query-planner quality keeps concerns clean.

### Non-goals

- no billing/export integration in this feature
- no hard cost enforcement (warn-only in first phase)

## Definition of Done

- token/cost fields are emitted when data is available
- unknown values are explicit when provider does not return usage
- run history stores cost-related metadata
- quality gates cover:
  - usage-present path
  - usage-missing path
  - pricing-config and no-pricing variants
