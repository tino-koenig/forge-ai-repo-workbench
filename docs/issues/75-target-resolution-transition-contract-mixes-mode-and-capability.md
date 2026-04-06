

# Target Resolution Transition Contract Mixes Mode and Capability

## Problem

Foundation 09 currently uses a transition validation interface that mixes **mode semantics** and **capability semantics**.

The function:

```python
validate_transition(source_mode, target_mode, context)
```

is called in practice with `target_mode` set to `request.capability`.

This leads to a conceptual mismatch:

- A *mode* describes a concrete execution flow (e.g. `query_v2`, `propose_v2`).
- A *capability* describes a higher-level intent or category of operation.

Treating a capability as a mode blurs the contract and weakens the clarity of transition validation.

## Why this matters

Foundation 09 is responsible for **controlled transitions between execution contexts**.

If mode and capability are mixed:

- transition rules become ambiguous,
- it becomes unclear what is actually being validated,
- later handoff logic (especially for multi-mode flows) becomes harder to reason about,
- future extensions (e.g. mode-specific policies) become fragile.

Clear separation is required to keep transitions predictable and testable.

## Evidence

- `validate_transition(source_mode, target_mode, ...)` expects modes.
- `resolve_from_run_reference(...)` passes `request.capability` as `target_mode`.
- Capability values do not necessarily map 1:1 to actual modes.

## Required behavior

- Transition validation must operate on **explicit mode identifiers**, not capabilities.
- Capability may still be used as input context, but must not replace mode in the transition contract.
- The interface must clearly distinguish:
  - `source_mode`
  - `target_mode`
  - optional `target_capability`

## Done criteria

- `validate_transition(...)` is called with real mode identifiers for both source and target.
- No call site passes capability where a mode is expected.
- If capability is needed, it is passed as a separate, explicitly named argument.
- Regression tests cover:
  - valid mode-to-mode transitions
  - blocked transitions
  - capability present but not used as mode

## Scope

This issue focuses on the **transition contract in Foundation 09**.
It does not require redesigning the full capability system.

## Suggested implementation direction

- Refactor `validate_transition(...)` signature if necessary to separate mode and capability.
- Update `resolve_from_run_reference(...)` to pass correct `target_mode`.
- If a mapping from capability → mode is needed, make it explicit and deterministic.
- Add tests that fail when capability is incorrectly used as a mode.

## How To Validate Quickly

1. Call `resolve_from_run_reference(...)` with a capability that does not map directly to a mode.
2. Ensure transition validation still operates on explicit modes.
3. Confirm that invalid transitions are blocked correctly.

## Known Limits / Notes

- This issue does not define how capabilities map to modes; it only enforces that they are not conflated.
- A future foundation may formalize capability-to-mode mapping if needed.
