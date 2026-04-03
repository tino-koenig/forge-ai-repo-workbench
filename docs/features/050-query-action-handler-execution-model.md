# Query Action Handler Execution Model

## Description

This feature defines concrete execution semantics for orchestrator actions in query mode.

Primary goals:
- map each allowed action to deterministic runtime behavior
- eliminate no-op orchestration actions
- keep action effects auditable

## Spec

### Scope

Define action handlers for query orchestration catalog:
- `search`
- `read`
- `explain`
- `rank`
- `summarize`
- `stop`

Each handler must declare:
- input state requirements
- deterministic effect on state
- budget cost accounting
- failure/fallback behavior
- source-scope behavior (`repo_only`, `framework_only`, `all`)

### Handler semantics

- `search`: extend candidate pool with bounded new matches
- `read`: collect additional evidence for selected candidates
- `explain`: derive explain feedback for selected candidates
- `rank`: recompute candidate order from current signals
- `summarize`: prepare final synthesis without modifying repo
- `stop`: terminate loop with explicit reason

Source-aware requirements:
- `search` and `rank` must preserve source attribution for each candidate/evidence
- default flow should prioritize repo candidates before framework expansion
- framework handlers must enforce dedicated caps to stay bounded on large ecosystems (for example TYPO3)

### Validation

- unsupported/invalid action for current state is rejected with policy-safe fallback
- handlers must not mutate repository files
- handlers must not mutate shared framework artifacts

## Design

### Why this feature

Without explicit handlers, orchestration decisions cannot reliably improve result quality. This feature turns orchestration from intent-only to execution-capable behavior.

### Non-goals

- no free-form action expansion at runtime
- no capability escalation via action choice
- no unbounded framework crawl caused by `search` action

## Definition of Done

- all catalog actions have implemented, tested handlers
- action execution changes query state deterministically
- handler-level budget accounting is visible in run metadata
- invalid actions degrade safely with explicit fallback reason
- source-aware execution and caps are enforced per handler

## Implemented Behavior (Current)

- Query orchestration executes explicit handlers for all catalog actions:
  - `search`: bounded candidate expansion from deterministic path-hint matches
  - `read`: bounded contextual evidence collection from selected candidates
  - `explain`: explain-feedback recomputation for top candidates
  - `rank`: deterministic rerank from current explain-feedback state
  - `summarize`: controlled finalization (`sufficient_evidence`)
  - `stop`: controlled finalization (`sufficient_evidence`)
- Unsupported/invalid actions degrade to `policy_blocked` with explicit handler diagnostics.
- Per-iteration metadata now includes handler execution info:
  - `handler_status`
  - `handler_detail`
  - `budget_files_used`
  - `budget_tokens_used`
- Source-scope behavior is deterministic for search:
  - default `repo_only`
  - bounded widening to `all` when top repo evidence is weak

## How To Validate Quickly

- Text diagnostics:
  - `forge --view full query "Where is query orchestration implemented?"`
  - inspect the `Action Orchestration` section for handler status/details
- JSON diagnostics:
  - `forge --output-format json query "Where is query orchestration implemented?"`
  - inspect `sections.action_orchestration.iterations[]` for handler metadata

## Known Limits / Notes

- `search` expansion remains intentionally conservative and path-hint based.
- Token accounting is bounded estimation, not provider token metering.
- Framework-specific dedicated caps are not yet separate config knobs; global orchestration budgets remain enforced.
