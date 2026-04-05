# Quality Gate Adaptive Query Feedback Uses Unstable LLM Question for Basic Fixture

## Problem

`gate_adaptive_query_explain_feedback` runs against the `basic_repo` fixture but uses the
question "In welchen Dateien wird ein LLM eingesetzt?".

The fixture does not contain meaningful LLM-related code paths, so retrieval can validly end
with no candidate locations (`done_reason=no_progress`) and an empty `explain_feedback` list.
The gate then fails although query behavior is contract-compliant.

## Scope

- keep validating adaptive explain-feedback structure and confidence fields.
- use a deterministic fixture-aligned query that reliably yields candidate locations.

## Acceptance Criteria

- `gate_adaptive_query_explain_feedback` passes deterministically in local and CI runs.
- gate still validates non-empty `explain_feedback`, `likely_locations`, and action orchestration presence.

## Resolution Notes

- switched gate query payload from the LLM-usage question to fixture-native `compute_price`.
