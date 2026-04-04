# Graph Health and Debug Surface

## Description

Add explicit graph health diagnostics for operators and CI.

Goals:
- make graph readiness visible,
- explain why graph was ignored or degraded,
- reduce deep manual inspection for graph-related failures.

## Spec

### Diagnostic content

Provide structured checks for:
- graph file presence and parseability
- schema/version validity
- node/edge counts and cap saturation status
- incremental reuse stats sanity (`reused_files`/`rebuilt_files`)
- framework ref status (loaded/missing/invalid)

### Interface

Expose in deterministic machine-readable form (and concise human output) via doctor/status command surface.

## Design

### Why this feature

Graph behavior is central for query/explain quality but currently hard to audit quickly when results degrade.

### Non-goals

- no runtime mutation of graph artifacts during diagnostics

## Definition of Done

- Graph health checks are available in CLI diagnostics.
- Output is actionable and references concrete artifact paths/ref ids.
- Regression tests assert warning/error paths for invalid graph scenarios.

## Implemented Behavior (Current)

- Query and explain now expose explicit framework-ref graph health signals in `sections.graph_usage`:
  - `framework_graph_refs_validation` (`valid` / `invalid` / `missing`)
  - `framework_graph_refs_loaded` (validated refs only)
  - `framework_graph_refs_warnings` (actionable warning messages with ref id/path context)
- Framework ref payloads are validated with the same minimal graph schema/version contract used for repo graph payloads.
- Invalid framework refs are rejected from active graph usage instead of being treated as loaded.

## How To Validate Quickly

1. Run `forge index` to generate a valid repo graph.
2. Configure framework refs in `.forge/config.toml` with one valid graph JSON and one invalid dict payload.
3. Run:
   - `forge --output-format json query "compute_price"`
4. Verify under `sections.graph_usage`:
   - invalid ref is absent from `framework_graph_refs_loaded`
   - `framework_graph_refs_validation` is `invalid`
   - warning list contains `invalid schema/version`.

## Known Limits / Notes

- The current health surface is integrated in query/explain graph usage reporting and regression gates; a dedicated doctor/status graph-health panel is still a follow-up improvement.
