# Preserve Token Usage Metadata in Redacted Protocol Logs

## Description

Keep non-secret token accounting fields visible in protocol logs while preserving strict secret redaction.

## Addresses Issues

- [Issue 8 - Protocol Redaction Overmasks `token_usage` Metadata](/Users/tino/PhpstormProjects/forge/docs/issues/8-protocol-redaction-overmasks-token-usage-metadata.md)

## Spec

- Redaction policy must distinguish credential tokens from usage counters.
- Keep sanitized `token_usage` fields (`prompt_tokens`, `completion_tokens`, `total_tokens`, `source`) in persisted protocol events.
- Continue masking secrets/auth tokens/API keys deterministically.

## Definition of Done

- Persisted `.forge/logs/events.jsonl` retains non-secret token usage counters when available.
- Privacy gate still passes for secret injection and bearer/api-key masking.
- Logs analytics can consume token/cost metadata consistently.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
