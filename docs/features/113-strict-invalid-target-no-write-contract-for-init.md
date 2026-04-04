# Strict Invalid-Target No-Write Contract for Init

## Description

Guarantee that init invalid-target failures remain diagnostic-only and cannot create filesystem artifacts.

## Addresses Issues

- [Issue 50 - Init Invalid Target Can Create Directory Tree via History Persistence](/Users/tino/PhpstormProjects/forge/docs/issues/50-init-invalid-target-can-create-directory-tree-via-history-persistence.md)

## Spec

- Ensure invalid target path failures short-circuit before any persistence path can create directories/files.
- Keep explicit error messaging and actionable next-step guidance.

## Definition of Done

- Failed init on missing target path leaves path absent.
- No `.forge` directories/files are created for invalid-target failures.
- Regression test enforces no-write guarantee.

## Implemented Behavior (Current)

- The behavior described in this feature is implemented and enforced in the current runtime path.
- Related quality-gate coverage is available in `scripts/run_quality_gates.py` for the addressed contract.

## How To Validate Quickly

1. Run `python3 scripts/run_quality_gates.py`.
2. Verify the related gate scenario for this feature passes.
3. Spot-check the corresponding command path (`forge` mode + JSON output) to confirm observable contract fields/behavior.

## Known Limits / Notes

- Validation is bounded by current fixture coverage; behavior outside covered fixtures should be rechecked when extending adjacent foundations.
