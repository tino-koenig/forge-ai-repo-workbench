

# Retrieval Empty Result Status Is Semantically Unclear

## Problem

Foundation 07 (Retrieval) can currently return an empty result set with a status that is semantically unclear (e.g. `ok` or `partial`) depending on code paths and diagnostics.

An empty result can mean different things:

- no relevant candidates were found,
- all candidates were filtered by scope or policy,
- all candidates were removed due to budget limits,
- an error prevented candidate generation.

These cases are not consistently distinguished in the resulting `status`.

## Why this matters

Downstream foundations depend on clear semantics:

- Foundation 08 (Ranking) needs to know whether it received a valid (but empty) set or a degraded/error state,
- Foundation 09 (Resolution) must decide whether to resolve, fallback, or surface ambiguity,
- Foundation 10 (Output Contract) and 11 (Observability) rely on consistent status to explain outcomes.

If "empty" is ambiguous:

- valid empty results can be misinterpreted as errors,
- real problems can be misinterpreted as normal empty outcomes,
- debugging and analytics become unreliable.

## Evidence

- `RetrievalOutcome.status` may be `ok` even when `candidates` and `evidence_items` are empty.
- Different empty-result paths (scope, policy, budget) are not always reflected distinctly in `status`.

## Required behavior

- Empty results must be **explicitly and consistently classified**.
- Status derivation must distinguish at least:
  - valid empty result (no matches) → `ok` or `partial` (by contract),
  - constrained empty result (scope/policy/budget) → `partial` or `blocked`,
  - failure to retrieve → `error`.
- Diagnostics must clearly indicate the reason for emptiness.

## Done criteria

- A single, centralized status-derivation function defines behavior for empty results.
- `RetrievalOutcome.status` is deterministic for identical inputs.
- Diagnostics include explicit reasons for empty results (e.g. `no_matching_sources`, `filtered_by_scope`, `budget_exhausted`).
- Regression tests cover:
  - no matches found (valid empty)
  - scope-filtered to empty
  - policy-blocked to empty
  - budget-truncated to empty
  - error during retrieval

## Scope

This issue focuses on **status semantics and diagnostics for empty retrieval results**.
It does not require changes to the retrieval algorithms themselves.

## Suggested implementation direction

- Centralize empty-result handling in a helper (e.g. `_status_for_empty_result(...)`).
- Evaluate causes in priority order (error > blocked > partial > ok).
- Ensure `source_usage` and `retrieval_diagnostics` provide sufficient context.
- Keep behavior deterministic and testable.

## How To Validate Quickly

1. Create a query that produces no matches.
2. Run `run_retrieval(...)`.
3. Verify that status and diagnostics clearly explain the empty result.
4. Repeat with scope/policy/budget constraints and confirm distinct statuses.

## Known Limits / Notes

- This issue does not enforce a single global choice between `ok` vs `partial` for valid empties; it enforces consistency and explicit diagnostics.
- Downstream foundations may refine behavior based on these clearer semantics.