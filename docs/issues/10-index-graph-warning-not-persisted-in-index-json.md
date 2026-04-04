# Index Graph Warning Not Persisted in `index.json`

## Problem

`forge index` writes `.forge/index.json` before graph build.
If graph build fails, code sets `data["graph"]["warning"]` afterward, but the updated payload is not written again.

Observed behavior:
- Console output can report `Graph cache: graph build skipped due to error: ...`.
- Persisted `.forge/index.json` may still miss the corresponding graph warning field.

This creates an observability gap between runtime output and persisted index metadata.

## Required behavior

- Graph warning/status metadata must be persisted in `.forge/index.json` when graph generation fails.
- Persisted index metadata and console output must be consistent for graph build outcome.

## Done criteria

- A forced graph-build-failure scenario produces a persisted graph warning in `.forge/index.json`.
- Existing successful graph path remains unchanged.
- A regression gate verifies warning persistence.

## Implemented Behavior (Current)

- `forge index` now rewrites `.forge/index.json` after a graph-build failure warning is attached to the in-memory payload.
- The persisted `index.json` graph metadata now includes `graph.warning` when graph generation is skipped due to an exception.
- Runtime console output and persisted index metadata stay aligned for graph-build failure outcomes.

## How To Validate Quickly

1. Trigger an index run with a forced graph-build failure (quality gate uses a patched `build_repo_graph` failure path).
2. Open `.forge/index.json`.
3. Verify:
   - `graph.warning` exists
   - value contains `graph build skipped due to error: ...`.

## Known Limits / Notes

- This fix addresses persistence of graph-build warning metadata in index artifacts; it does not attempt automatic recovery or retry of graph generation.
