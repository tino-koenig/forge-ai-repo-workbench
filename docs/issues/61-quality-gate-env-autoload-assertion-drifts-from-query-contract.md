# Quality Gate `.env` Autoload Assertion Drifts from Query LLM Contract

## Problem

`gate_env_file_autoload` failed with:
- `.env autoload should preserve provider from config`

Reason:
- gate asserted legacy `sections.llm_usage.provider` field.
- current query contract exposes provider details at stage-level usage (`query_planner.usage`, `action_orchestration.usage`).

## Scope

- align `.env` autoload gate assertions with current stage-level query contract.
- preserve original intent: config provider remains effective and `.env` supplies missing API key.

## Acceptance Criteria

- `gate_env_file_autoload` passes.
- planner stage reports `provider=openai_compatible`.
- planner stage usage is `used=true` when key is loaded from `.env`.

## Resolution Notes

- replaced legacy top-level provider assertion with planner-stage provider/usage assertions.
