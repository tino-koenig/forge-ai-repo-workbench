# Foundation Normalize Patterns Scalar Input Crash

## Problem

Foundation pattern normalization currently crashes when `_normalize_patterns` receives scalar input where pattern collections are expected.

Instead of returning a controlled contract diagnostic, the current implementation assumes iterable input and can raise a runtime `TypeError`. This means malformed caller input can escape the normal validation path and fail as an internal runtime exception.

## Why this matters

- A single malformed input can crash the flow instead of producing a controlled rejection.
- Callers cannot reliably distinguish invalid user input from an internal implementation fault.
- The Foundation boundary becomes less trustworthy because invalid input is not handled deterministically.
- Downstream diagnostics and observability lose precision when a contract violation is surfaced as a generic runtime failure.

## Evidence

- `_normalize_patterns` currently expects iterable input and does not fully defend against scalar values.
- Scalar inputs such as strings, numbers, booleans, or other non-collection values can reach normalization.
- In those cases, the code raises `TypeError` instead of returning a controlled validation result or explicit contract diagnostic.

## Required behavior

- Scalar input must be handled deterministically at the normalization boundary.
- Invalid scalar shapes must return explicit diagnostics instead of uncaught exceptions.
- Supported input shapes must be defined clearly and enforced consistently.
- Any coercion behavior must be explicit, intentional, and covered by regression tests.

## Done criteria

- `_normalize_patterns` no longer raises unhandled exceptions for scalar input.
- The behavior for unsupported scalar values is explicit and stable.
- Regression coverage includes at least:
  - string input
  - numeric input
  - boolean input
  - `None` / null-like input
  - valid iterable/list input preserving existing behavior
- Diagnostics clearly distinguish invalid input shape from internal failure.

## Scope

This issue is limited to Foundation input-shape hardening for pattern normalization.

It does not change pattern matching semantics, matching strategy, or broader workspace policy behavior.

## Implemented Behavior (Current)

- `_normalize_patterns` now catches non-iterable scalar input shapes at the normalization boundary.
- Unsupported scalar inputs no longer raise `TypeError`; they return an empty normalized pattern set and emit a structured `ScopeDiagnostic` with code `invalid_pattern_input_shape`.
- Existing supported behavior is preserved:
  - `None` remains a valid empty input,
  - string input remains a single-pattern form,
  - iterable/list inputs continue to normalize as before.
- `resolve_workspace_context` now forwards pattern-source field names into normalization so diagnostics identify the exact offending input key.

## Suggested implementation direction

- Add early type and shape guards at the `_normalize_patterns` entry boundary.
- Reject unsupported scalar inputs with controlled diagnostics before iteration begins.
- Only coerce input into canonical list form when that behavior is explicitly part of the contract.
- Preserve current behavior for valid list-like inputs unless an intentional contract change is made.

## How To Validate Quickly

1. Run normalization with valid list-like pattern input and confirm unchanged behavior.
2. Run normalization with scalar inputs such as `"x"`, `1`, `True`, and `None`.
3. Confirm that each invalid scalar case returns a deterministic diagnostic instead of crashing.
4. Confirm that runtime failures are no longer possible from this input-shape path alone.

## Known Limits / Notes

- This issue is about robustness and contract handling at the normalization boundary.
- It should not broaden accepted pattern syntax unless that is made explicit in the contract.
- Broader workspace policy validation remains out of scope.
