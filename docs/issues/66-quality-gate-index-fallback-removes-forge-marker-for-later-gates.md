# Quality Gate Index Fallback Removes `.forge` Marker for Later Gates

## Problem

`gate_fallback_with_and_without_index` deletes `repo_root/.forge` to validate index-missing fallback behavior.

Because all gates share the same temporary `repo_root` fixture, removing `.forge` without restoring
it breaks subsequent gates that require the repository marker (for example `query` invocations with
`--repo-root`).

## Scope

- keep fallback-without-index assertions unchanged.
- restore shared fixture baseline after the gate completes.

## Acceptance Criteria

- `gate_fallback_with_and_without_index` still verifies "Index: not available|skipped" outputs.
- full `scripts/run_quality_gates.py` run no longer fails with "nearest .forge/ marker missing" after this gate.

## Resolution Notes

- after deleting `.forge` to remove index artifacts, immediately recreate `repo_root/.forge` marker before executing fallback checks.
