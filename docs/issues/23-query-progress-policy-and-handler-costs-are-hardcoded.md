# Query Progress Policy and Handler Costs Are Hardcoded

## Problem

Key query orchestration controls are hardcoded in mode logic instead of centralized config/runtime settings.
This reduces transparency and tuning ability across repositories/profiles.

## Evidence

- In `modes/query.py`, constants are hardcoded in runtime flow:
  - `no_progress_streak_limit = 2`
  - `progress_threshold = 1.5`
  - fixed token/file cost increments for handlers
  - fixed read batch limits
- Existing config contains budgets but not these policy/cost coefficients.

## Required behavior

- Progress policy and handler accounting coefficients should be externally configurable.
- Defaults must remain deterministic and documented.
- Settings resolution should use runtime settings foundation precedence.

## Done criteria

- Query progress and handler cost parameters are configurable via canonical settings keys.
- Output reports effective policy sources (default/repo/user/session/cli).
- Regression gates cover non-default policy behavior.

## Linked Features

- [Feature 080 - Query Orchestration Policy Settings and Source-Traceable Resolution](/Users/tino/PhpstormProjects/forge/docs/features/080-query-orchestration-policy-settings-and-source-traceable-resolution.md)

## Implemented Behavior (Current)

- Query orchestration progress policy and handler cost coefficients are now runtime-resolved, not hardcoded literals.
- Output includes effective values and resolved sources under `sections.action_orchestration.progress_policy` and `sections.action_orchestration.handler_policy`.
- Dedicated gate verifies both custom override behavior and default fallback behavior.

## How To Validate Quickly

- Add custom values to `.forge/runtime.toml` for query orchestrator policy keys.
- Run:
  - `python3 forge.py --output-format json --llm-provider mock query "compute_price"`
- Check:
  - policy values reflect runtime override
  - source fields show `repo`
- Remove overrides and rerun:
  - defaults are restored and sources become `default`

## Known Limits / Notes

- This issue addresses policy/cost configurability and source traceability, not planner decision quality.
