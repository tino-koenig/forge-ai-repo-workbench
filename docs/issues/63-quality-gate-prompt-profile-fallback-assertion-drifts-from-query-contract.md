# Quality Gate Prompt-Profile Fallback Assertion Drifts from Current Query Contract

## Problem

`gate_prompt_profile_policy` validates invalid prompt-profile fallback via `query`.

The gate expects:
- `sections.llm_usage.used == false`
- fallback reason contains `not allowed for capability 'query'`

But current query contract can still report LLM usage via planner/orchestrator stages, even when a prompt profile is incompatible for summary refinement.
Result: the gate fails although prompt-profile compatibility logic itself is correct.

## Scope

- keep validating prompt-profile compatibility fallback behavior.
- move mismatch assertion to a capability where prompt-profile compatibility is directly reflected in the top-level LLM usage contract.

## Acceptance Criteria

- `gate_prompt_profile_policy` passes deterministically.
- mismatch check asserts incompatible `review_strict` profile fallback against `describe` capability.

## Resolution Notes

- keep default-capability profile assertion for `describe` unchanged.
- replace mismatch probe command from `query` to `describe`.
- assert fallback reason contains `not allowed for capability 'describe'`.
