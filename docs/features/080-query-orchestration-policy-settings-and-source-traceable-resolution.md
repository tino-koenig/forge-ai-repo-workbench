# Query Orchestration Policy Settings and Source-Traceable Resolution

## Description

Externalize query orchestration progress policy and handler-cost coefficients into canonical runtime settings.

Goals:
- remove hidden hardcoded policy constants
- make tuning transparent and reproducible
- integrate with runtime settings precedence/source tracing

## Addresses Issues

- [Issue 23 - Query Progress Policy and Handler Costs Are Hardcoded](/Users/tino/PhpstormProjects/forge/docs/issues/23-query-progress-policy-and-handler-costs-are-hardcoded.md)

## Spec

### New settings scope

Add canonical keys for query orchestration policy and accounting, for example:
- `query.orchestrator.progress.threshold`
- `query.orchestrator.progress.no_progress_streak_limit`
- `query.orchestrator.handler.read.max_batch`
- `query.orchestrator.handler.read.token_cost_per_line`
- `query.orchestrator.handler.search.token_cost_per_match`
- `query.orchestrator.handler.explain.base_token_cost`

### Resolution and observability

- Resolve via runtime settings foundation precedence (cli > session > repo > user > toml > default).
- Expose effective values and their sources in query output sections.

### Compatibility

- Defaults preserve current behavior unless overridden.

## Definition of Done

- Hardcoded progress/cost constants in query orchestration are replaced by resolved settings.
- `forge get --source` can show origin for these keys.
- Regression gates cover custom policy behavior and fallback-to-default behavior.

## Implemented Behavior (Current)

- Query orchestration now resolves progress/cost policy via runtime settings foundation for:
  - `query.orchestrator.progress.threshold`
  - `query.orchestrator.progress.no_progress_streak_limit`
  - `query.orchestrator.handler.read.max_batch`
  - `query.orchestrator.handler.read.token_cost_per_line`
  - `query.orchestrator.handler.search.token_cost_per_match`
  - `query.orchestrator.handler.explain.base_token_cost`
- `sections.action_orchestration` now exposes effective policy values and resolved sources (`default|user|repo|session|session:<name>|cli`).
- Runtime key normalization now maps underscore-preserving query-orchestrator keys deterministically.

## How To Validate Quickly

- Configure repo runtime (`.forge/runtime.toml`) with non-default policy values.
- Run:
  - `python3 forge.py --output-format json --llm-provider mock query "compute_price"`
- Verify:
  - `sections.action_orchestration.progress_policy` shows configured values and `sources=*repo*`
  - `sections.action_orchestration.handler_policy` shows configured handler coefficients and sources
- Remove runtime overrides and rerun:
  - values fall back to documented defaults with source `default`

## Known Limits / Notes

- Token accounting caps (for example search expansion cap and explain max-token guard) remain bounded by orchestration budget constraints.
