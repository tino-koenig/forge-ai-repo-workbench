# Graph Schema Validation and Compatibility Contract

## Description

Introduce a shared deterministic graph validation contract for repo and framework graph artifacts before runtime consumption.

Goals:
- enforce minimum schema integrity,
- enforce compatible `graph_version`,
- make `graph_usage` fields truthful and auditable.

## Spec

### Validation scope

Apply to:
- `.forge/graph.json` loading
- framework refs in `[graph.framework_refs]`

### Minimal required fields

Validate presence/type for:
- `graph_version`
- `source_type`
- `source_id`
- `nodes` (list)
- `edges` (list)
- `stats` (object)

### Compatibility

- supported version set is explicit
- incompatible versions are rejected with deterministic warning

### Reporting

- runtime outputs include graph validation outcome per source
- invalid sources are excluded from `*_graph_*_loaded` fields

## Design

### Why this feature

Without validation, malformed graph payloads are silently treated as loaded, causing misleading confidence and provenance.

### Non-goals

- no auto-migration in first step
- no implicit rewriting of invalid framework artifacts

## Definition of Done

- Shared validator exists and is used by repo and framework graph loaders.
- Consumers only use validated graph payloads.
- JSON/full outputs expose validation warnings and acceptance state.
- Regression gates cover malformed dict payloads and incompatible versions.

## Implemented Behavior (Current)

- Added deterministic repo-graph validator at load time with required field/type checks and explicit supported-version enforcement.
- Repo graph loading now returns warnings for invalid schema/version and rejects invalid payloads as unusable.
- Query and explain now expose repo-graph validation status in `sections.graph_usage`:
  - `repo_graph_loaded`
  - `repo_graph_validation` (`valid|invalid|missing`)
  - `repo_graph_warnings`
- Added regression gate `gate_graph_schema_validation_and_compatibility`.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_graph_schema_validation_and_compatibility` passes.

## Known Limits / Notes

- This increment hardens repo graph schema/version loading first; framework-ref payload validation is extended in a follow-up increment.
