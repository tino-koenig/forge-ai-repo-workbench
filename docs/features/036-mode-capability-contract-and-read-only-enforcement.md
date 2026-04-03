# Mode Capability Contract and Read-Only Enforcement

## Description

This feature defines a strict capability contract per Forge mode.

Primary goals:
- preserve explicit mode semantics
- ensure `query` is always read-only
- prevent prompt text from escalating capabilities

## Spec

### Scope

Define a central capability matrix for all modes.

Examples:
- `query`: read-only actions only
- `review`: read-only actions only
- `index`: index write actions only
- `fix` (later): bounded repo write actions

### Contract rules

- Mode capability is resolved before planning starts.
- User text cannot override mode capabilities.
- Action eligibility is checked at both plan time and run time.

### Query hard guarantee

`query` must never perform repo writes, even when user input explicitly asks for edits.

If user intent requests write behavior while in `query`, Forge must:
- continue with read-only analysis where possible
- return an explicit mode-boundary note

### Enforcement points

- planner gate: cannot schedule disallowed actions
- executor gate: rejects any disallowed action before execution

Both gates must use the same canonical matrix.

### Failure behavior

Disallowed action attempt yields:
- structured policy violation event
- human-readable explanation with mode and blocked action
- no partial write side effects

## Design

### Why this feature

Forge depends on explicit, trustworthy mode boundaries. Without hard policy enforcement, automatic workflows can become unpredictable.

### Non-goals

- no natural-language permission inference
- no implicit mode switching
- no hidden policy exceptions

## Definition of Done

- a central mode-to-action capability matrix is implemented
- planner and executor both enforce the same capability rules
- `query` is proven read-only by regression tests, including adversarial prompts
- policy violations are visible in run output and logs
