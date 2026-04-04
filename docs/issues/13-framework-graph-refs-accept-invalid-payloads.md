# Framework Graph Refs Accept Invalid Payloads

## Problem

Framework graph references are accepted as long as JSON parses to a dict. Required graph schema fields are not validated.

Observed behavior:
- `load_framework_graph_references` accepts payload like `{"foo": 1}` as loaded.
- Query output reports `framework_graph_refs_loaded` including invalid refs.
- No warning indicates schema invalidity, so graph provenance is overstated.

## Required behavior

- Validate framework graph payloads with the same minimal contract used for repo graph loading.
- Reject invalid payloads and emit explicit warnings per ref.
- Ensure `framework_graph_refs_loaded` includes only valid/usable refs.

## Done criteria

- Invalid framework graph JSON objects are excluded from loaded refs.
- Warnings indicate `invalid schema/version` with ref id and path.
- Regression gate covers malformed-but-dict payload acceptance bug.

## Implemented Behavior (Current)

- Framework graph refs are now validated with the same minimal graph contract as repo graph loading (including schema fields and supported `graph_version`).
- Invalid refs are excluded from `framework_graph_refs_loaded`.
- Query/explain expose framework-ref validation and warnings in `sections.graph_usage`:
  - `framework_graph_refs_validation`
  - `framework_graph_refs_warnings`
- Malformed refs emit explicit warnings that include ref id and path context.

## How To Validate Quickly

1. Build an index to create `.forge/graph.json`:
   - `forge index`
2. Add one valid and one invalid framework ref in `.forge/config.toml` under `[graph.framework_refs]`.
3. Run:
   - `forge --output-format json query "compute_price"`
4. Confirm:
   - `sections.graph_usage.framework_graph_refs_loaded` excludes invalid refs.
   - `sections.graph_usage.framework_graph_refs_warnings` contains an `invalid schema/version` warning.

## Known Limits / Notes

- Validation applies to graph payload contract compatibility; it does not currently enforce domain-specific framework constraints beyond that shared contract.
