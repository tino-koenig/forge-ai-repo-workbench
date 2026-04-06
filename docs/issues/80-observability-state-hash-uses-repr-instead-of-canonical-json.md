

# Observability State Hash Uses repr Instead of Canonical JSON

## Problem

Foundation 11 (Observability) currently computes state hashes using `repr(...)` instead of a canonical JSON serialization.

This approach is not guaranteed to be stable across:

- Python versions,
- dictionary key ordering differences,
- minor representation changes of objects.

As a result, identical logical states may produce different hashes.

## Why this matters

The state hash is used for:

- trace correlation,
- change detection,
- reproducibility checks,
- debugging and analysis.

If hashing is not deterministic:

- identical runs may appear different,
- debugging becomes harder,
- trace comparisons become unreliable,
- observability loses trustworthiness.

## Evidence

- `_stable_hash(...)` currently uses `repr(...)`.
- `repr(...)` is not a canonical serialization format.
- It can vary based on runtime environment and object representation.

## Required behavior

- State hashing must be deterministic for identical logical input.
- Hash input must be based on a canonical, stable serialization format.
- Key ordering must not affect the resulting hash.

## Done criteria

- `_stable_hash(...)` uses JSON serialization with:
  - `sort_keys=True`
  - stable separators
- The same logical state always produces the same hash.
- Regression tests confirm identical hashes for:
  - same data with different dict insertion orders
  - repeated runs

## Scope

This issue is limited to **state hash generation in Foundation 11**.

## Suggested implementation direction

- Replace `repr(...)` with `json.dumps(...)`.
- Ensure:
  - keys are sorted
  - non-serializable objects are normalized before hashing
- Keep hashing logic centralized in a single helper.

## How To Validate Quickly

1. Create two logically identical state objects with different key insertion orders.
2. Compute hash for both.
3. Confirm hashes are identical.

## Known Limits / Notes

- Objects must be normalized before serialization if they are not JSON-compatible.
- This change improves determinism but does not change event semantics.
