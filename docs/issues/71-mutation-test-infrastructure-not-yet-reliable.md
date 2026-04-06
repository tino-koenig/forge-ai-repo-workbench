

# Mutation Test Infrastructure Is Not Yet Reliable

## Problem

The current mutation testing setup using `mutmut` is not yet producing reliable or actionable results.

The initial run fails during the sanity check phase with:

> "FAILED: Unable to force test failures"

This means the mutation testing tool cannot confirm that the test suite is capable of detecting introduced changes, and therefore cannot provide a meaningful mutation score.

## Why this matters

Mutation testing is intended to measure the **strength of the test suite**, not just coverage.

If the infrastructure is not reliable:

- we cannot trust mutation scores,
- we cannot identify weak or missing tests,
- regressions may go undetected even if coverage looks high,
- quality gates based on mutation testing cannot be introduced.

A broken mutation test setup gives a false sense of completeness.

## Evidence

- `mutmut` initialization runs, but the sanity check fails.
- The tool is unable to enforce a failing test when expected.
- No valid mutation score is produced.

## Required behavior

- Mutation testing must run successfully on the implemented foundation modules.
- The sanity check must pass (mutations must be detectable by tests).
- Mutation runs must produce a stable and reproducible mutation score.

## Done criteria

- `mutmut` completes a full run without sanity check failures.
- A valid mutation score is produced.
- At least one mutation is correctly detected and fails tests.
- Mutation testing can be re-run deterministically.

## Scope

This issue focuses on the **mutation testing infrastructure**, not on improving test coverage itself.

## Implemented Behavior (Current)

- `mutmut` is now configured explicitly in `pyproject.toml` under `[tool.mutmut]`.
- Mutation scope is deterministic and foundation-focused via an explicit `paths_to_mutate` list (stable implemented foundation subset in `core/`).
- Test execution scope is deterministic via explicit `tests_dir` entries (foundation test modules).
- This removes implicit path guessing (previously mutating `forge/`) and aligns mutation execution with the test surface that exercises foundation code.
- Validation commands now use the `mutmut` entrypoint (`.venv/bin/mutmut ...`) to avoid `python -m mutmut` double-import side effects in trampoline execution.

## Suggested implementation direction

- Verify test discovery and execution environment used by `mutmut`.
- Ensure tests can fail when code is modified (sanity check must pass).
- Limit mutation scope initially to foundation modules.
- Align `mutmut` execution environment with the one used for pytest (including paths and fixtures).

## How To Validate Quickly

1. Remove previous mutation workspace artifacts:
   - `rm -rf mutants`
2. Run mutation testing:
   - `.venv/bin/mutmut run --max-children 1 core.mode_execution_foundation.x__derive_terminal_status__mutmut_1`
3. Confirm sanity check passes (no `FAILED: Unable to force test failures`).
4. Confirm at least one mutation is executed and reported (`Mutant results` with killed/survived marker).
5. Optional: inspect current mutation state:
   - `.venv/bin/mutmut results`

## Known Limits / Notes

- Mutation testing may initially be slower or limited in scope.
- This issue does not require full-repo mutation coverage yet.
- Focus is on making the mutation infrastructure usable and trustworthy first.
