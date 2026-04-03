# Explicit Mode Transition Workflows

## Description

This feature defines explicit, policy-controlled mode transitions for multi-step workflows such as `fix -> review -> test`.

Primary goals:
- support useful chained workflows
- preserve mode boundaries at every step
- keep transition logic inspectable

## Spec

### Scope

Introduce a transition policy graph that declares which mode transitions are allowed.

Example allowed transitions:
- `fix -> review`
- `review -> test`
- `test -> fix` (conditional)

Transitions not declared are disallowed.

### Transition gates

Each transition may require gate conditions, such as:
- review findings severity threshold
- test failure presence
- explicit user confirmation policy (configurable)

### Capability continuity

After transition, the target mode capability contract applies immediately.

Example:
- `fix` can write within scope
- `review` is read-only even when entered from `fix`

### Traceability

Run output and logs must record:
- source mode
- target mode
- transition reason
- gate decisions

## Design

### Why this feature

Chained workflows are useful, but without explicit transition policy they become opaque and risky. This feature keeps orchestration understandable and controlled.

### Non-goals

- no fully autonomous unrestricted mode hopping
- no bypass of per-mode capability enforcement
- no hidden transition heuristics

## Definition of Done

- transition policy graph exists and is validated
- disallowed transitions fail with clear policy errors
- allowed transitions enforce gate conditions and are fully logged
- end-to-end fixtures cover `fix -> review -> test` control flow
