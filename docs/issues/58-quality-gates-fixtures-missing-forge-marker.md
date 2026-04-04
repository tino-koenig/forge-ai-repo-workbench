# Quality Gates Fixtures Missing `.forge` Marker after Repo-Context Discovery Enforcement

## Problem

Quality-gate smoke execution failed in CI with:
- `No initialized Forge repository found (nearest .forge/ marker missing)`

Reason:
- temporary fixture repositories created by `scripts/run_quality_gates.py` did not include a `.forge/` marker.
- CLI repository resolution now requires the marker and fails before capability execution.

## Scope

- make temporary quality-gate fixture repos satisfy current repository-context precondition.
- keep gate behavior focused on capability checks rather than bootstrap precondition failures.

## Acceptance Criteria

- `gate_behavior_smoke` no longer fails on missing `.forge` marker.
- quality-gate fixture setup always creates `.forge/` in copied temp repos.
- existing init-specific non-mutating tests still use separate explicit empty repos.

## Resolution Notes

- updated fixture setup in `run_all_gates()` to create `.forge/` marker directories for all copied temp repos before gate execution.
