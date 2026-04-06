

# Evidence Ranking Can Downgrade Error Diagnostics to Partial Status

## Problem

Foundation 08 (Evidence Ranking) can currently derive an overall `status` of `partial` even when underlying diagnostics indicate a real error condition.

This happens when the status derivation logic gives precedence to softer signals (e.g. missing evidence or incomplete data) over harder error diagnostics.

As a result, an execution that should be considered `error` can be surfaced as `partial`.

## Why this matters

Ranking is not just a convenience layer; it feeds directly into:

- Target Resolution (Foundation 09),
- Output Contract (Foundation 10),
- Observability (Foundation 11).

If error conditions are downgraded:

- downstream foundations may treat faulty results as usable,
- incorrect targets may be resolved from invalid candidate sets,
- debugging becomes misleading because real errors are masked,
- contract semantics between foundations become inconsistent.

Error conditions must not be softened silently.

## Evidence

- `RankingOutcome.status` is derived from a mix of:
  - retrieval status,
  - candidate-level status,
  - diagnostics.
- In some paths, the presence of partial data leads to `partial` even when diagnostics include error-level issues.

## Required behavior

- Error diagnostics must take precedence over partial conditions.
- If any candidate or ranking step produces an error-level diagnostic, the overall `RankingOutcome.status` must be `error`.
- Status derivation must follow a strict priority, for example:

```text
error > blocked > partial > ok
```

- The behavior must be deterministic and consistent across all ranking paths.

## Done criteria

- `RankingOutcome.status` is never `partial` if error diagnostics are present.
- Status priority is explicitly defined and enforced in a single place.
- Regression tests cover:
  - pure partial conditions
  - error conditions without partial signals
  - mixed partial + error conditions (must resolve to `error`)

## Scope

This issue is limited to **status derivation in Foundation 08**.
It does not require changes to the scoring model itself.

## Suggested implementation direction

- Centralize status derivation (e.g. `_derive_outcome_status(...)`).
- Evaluate diagnostics first and escalate to `error` if needed.
- Only derive `partial` if no error-level diagnostics are present.
- Ensure candidate-level errors propagate correctly to the outcome.

## How To Validate Quickly

1. Create a ranking scenario with at least one error-level diagnostic.
2. Run `rank_evidence(...)`.
3. Confirm that `RankingOutcome.status == "error"`.
4. Add additional partial signals and confirm that the result still remains `error`.

## Known Limits / Notes

- This issue does not redefine what counts as an error diagnostic, only how such diagnostics affect status.
- Downstream foundations may rely on this stricter behavior for safer execution.