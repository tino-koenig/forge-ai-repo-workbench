# Graph Cache Schema/Version Not Validated on Load

## Problem

Graph consumers treat `.forge/graph.json` as loaded when payload is any JSON object, without validating required schema fields or `graph_version` compatibility.

Observed behavior:
- `core/graph_cache.py::load_repo_graph` returns payload for any dict.
- Query/Explain report `graph_usage.repo_graph_loaded=true` even when required fields are missing or `graph_version` is incompatible.
- Runtime falls back silently to non-graph behavior in edge extraction paths without surfacing a contract warning.

This creates misleading observability and weakens graph contract guarantees.

## Required behavior

- Validate repo graph payload on load against minimal required schema and supported `graph_version`.
- Mark invalid/incompatible graph as unavailable for consumers.
- Emit explicit warnings in uncertainty/diagnostics with actionable reason.

## Done criteria

- Invalid repo graph payload is rejected deterministically.
- `graph_usage.repo_graph_loaded` reflects validated usability (not just JSON parse success).
- Regression gate covers malformed/missing-fields/incompatible-version scenarios.

## Implemented Behavior (Current)

- Repo graph loading now validates required schema fields and compatible `graph_version` before accepting payloads.
- Invalid/incompatible repo graph payloads are rejected deterministically and surfaced as explicit warnings.
- Query/explain `graph_usage` now reflects validated graph readiness (not mere JSON parse success).
- Regression coverage added via `gate_graph_schema_validation_and_compatibility`.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_graph_schema_validation_and_compatibility` passes.

## Known Limits / Notes

- Validation in this increment applies to repo graph load path; framework-ref schema validation is handled separately.
