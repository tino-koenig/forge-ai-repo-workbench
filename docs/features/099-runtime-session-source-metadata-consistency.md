# Runtime Session Source Metadata Consistency

## Description

Align runtime diagnostics so session source origin metadata is consistent with actual source used in resolution.

## Addresses Issues

- [Issue 4 - Runtime Scope Path Session Source Mismatch](/Users/tino/PhpstormProjects/forge/docs/issues/4-runtime-scope-path-session-source-mismatch.md)

## Spec

- If named session values participate, diagnostics should expose named-session origin (or merged origins) in session scope metadata.
- If env session payload participates, diagnostics should expose env origin explicitly.
- Source metadata should remain deterministic and human-auditable.

## Definition of Done

- `doctor` runtime section no longer reports contradictory session origin metadata.
- `sources.*` and `scope_paths.session` (or equivalent metadata field) are semantically aligned.
- Quality gate asserts consistency.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
