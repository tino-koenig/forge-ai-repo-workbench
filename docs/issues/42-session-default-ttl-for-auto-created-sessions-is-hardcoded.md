# Session Default TTL for Auto-Created Sessions Is Hardcoded

## Problem

Auto-created sessions always use a fixed default TTL constant (60 minutes) with no runtime/config setting.
This limits control for teams that need shorter or longer inactivity windows.

## Evidence

- `ensure_active_session` creates sessions with `DEFAULT_TTL_MINUTES`.
- No canonical runtime setting key exists for session default TTL.
- Current runtime registry contains only output/llm/execution/access families.

## Required behavior

- Default TTL for auto-created sessions should be configurable via canonical runtime/config setting(s), with deterministic fallback to 60.
- Source tracing should reveal where effective TTL came from.

## Done criteria

- New canonical session TTL setting(s) are supported and validated.
- Auto-create path uses resolved effective TTL.
- `doctor`/`get --source` expose TTL source visibility.

## Linked Features

- [Feature 101 - Configurable Session TTL Policy via Runtime Settings](/Users/tino/PhpstormProjects/forge/docs/features/101-configurable-session-ttl-policy-via-runtime-settings.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
