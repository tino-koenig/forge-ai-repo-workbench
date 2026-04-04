# Query Summary Disabled Counted as LLM Fallback in Log Analytics

## Problem

When query summary refinement is disabled by policy (for example JSON output), protocol events still emit `summary_refinement` as `llm` with terminal `fallback`.
This inflates fallback analytics in feature 033 despite no real failed LLM call.

Observed behavior:
- Query JSON sets `sections.llm_usage` with `attempted=false`, `used=false`, fallback reason ("summary refinement disabled for json output").
- Event conversion still emits llm started+fallback entries for that stage.
- `forge logs --step-type llm stats` reports non-trivial fallback rates from policy-disabled paths.

## Required behavior

- Policy-disabled/non-attempted LLM stages must not be counted as failure/fallback events in operational analytics.
- Fallback metrics should represent actual attempted LLM instability, not expected disabled behavior.
- If disabled-stage visibility is desired, use explicit non-llm policy events or separate counters.

## Done criteria

- Query JSON mode no longer adds synthetic llm fallback for disabled summary refinement.
- `logs stats` fallback rate for simple mock query scenarios is not inflated by disabled stages.
- Existing llm fallback reporting still works for real planner/orchestrator/provider failures.


## Linked Features

- [Feature 106 - Policy-Disabled LLM Events Must Not Inflate Fallback Analytics](/Users/tino/PhpstormProjects/forge/docs/features/106-policy-disabled-llm-events-must-not-inflate-fallback-analytics.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
