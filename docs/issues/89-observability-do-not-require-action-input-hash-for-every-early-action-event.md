# Observability Do Not Require action_input_hash for Every Early action_* Event

## Problem

Observability currently requires `action_input_hash` for all `action_*` events.

In early action lifecycle events (for example planning-stage events), a stable action input hash may not yet exist. The strict requirement can therefore reject otherwise valid telemetry events.

## Why this matters

- Legitimate early action events can fail at runtime with validation errors.
- Observability becomes brittle at precisely the stage where diagnostic traceability is needed.
- Instrumentation code may need artificial placeholder values just to satisfy schema checks.
- Event quality can degrade if callers emit synthetic hashes rather than truthful metadata.

## Evidence

- Validation enforces `action_input_hash` for every event type prefixed with `action_`.
- Early action events are semantically different from execution events and may not have finalized action input payloads yet.

## Required behavior

- `action_input_hash` must remain required where semantically necessary (execution/blocking events with stable input context).
- Early action events without stable input must be allowed without forcing placeholder hashes.
- Schema behavior must remain deterministic and explicit.

## Done criteria

- Validation no longer rejects valid early action events solely because of missing `action_input_hash`.
- Events that semantically require the hash still enforce it.
- Tests cover both:
  - accepted early-action event without hash
  - rejected event where hash is still required.

## Scope

This issue is limited to observability event-schema validation semantics for `action_input_hash`.

It does not include redesign of the event catalog, redaction strategy, retention, or run-summary aggregation.

## Linked Features

- _To be defined during implementation._

## Suggested implementation direction

- Replace prefix-wide `action_*` requirement with a narrower event-type rule based on semantic phase.
- Document the requirement boundary in code comments and tests.

## Implemented Behavior (Current)

- Observability now requires `action_input_hash` only for execution-phase action events:
  - `action_executed`
  - `action_noop`
  - `action_blocked`
- Early lifecycle action events such as `action_planned` no longer fail schema validation when no stable action input hash is available.
- Existing orchestration-correlation requirements (`iteration_id`, `policy_version`, `settings_snapshot_id`) remain unchanged.

## How To Validate Quickly

1. Emit an early action event without `action_input_hash`.
2. Confirm event creation/logging succeeds.
3. Emit an execution/blocking action event without hash (if semantically required).
4. Confirm validation still rejects that malformed case.

## Known Limits / Notes

- This issue adjusts requirement scope, not event payload content quality in general.
- Any future event-type additions should explicitly declare whether they require `action_input_hash`.
