# Bounded LLM Action Orchestration

## Description

This feature introduces LLM-guided next-step selection within strict Forge guardrails.

Primary goals:
- allow adaptive step sequencing
- keep control explicit and auditable
- guarantee bounded execution

## Spec

### Scope

Add an LLM decision stage that can choose the next action from a predefined action catalog for the current mode.

The LLM may decide:
- continue with another allowed action
- stop with a completion reason

### Action catalog

Actions must be typed and schema-validated.

For read-only modes, catalog examples include:
- `search`
- `read`
- `explain`
- `rank`
- `summarize`
- `stop`

Free-form tool calls are not allowed.

### Decision contract

Each decision must include:
- `decision` (`continue|stop`)
- `next_action` (when continue)
- `reason`
- `confidence`

Invalid decisions trigger deterministic fallback logic.

### Budget and termination

Execution must be bounded by explicit limits:
- `max_iterations`
- `max_files`
- `max_tokens`
- `max_wall_time_ms`

Run termination must include `done_reason`, such as:
- `sufficient_evidence`
- `budget_exhausted`
- `policy_blocked`

## Design

### Why this feature

Static pipelines are predictable but can miss relevant evidence for harder queries. Bounded LLM orchestration improves usefulness while preserving explicit control.

### Non-goals

- no autonomous unrestricted tool use
- no bypass of mode capability gates
- no hidden retry loops

## Definition of Done

- LLM next-action selection is limited to a mode-scoped catalog
- invalid LLM decisions are safely rejected with deterministic fallback
- all runs terminate within configured budgets
- run output includes explicit decision rationale and done reason
