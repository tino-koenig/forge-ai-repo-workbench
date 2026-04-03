# Index Explain Summary Enrichment

## Description

This feature allows `forge index` to enrich index entries with compact explain summaries for faster, higher-quality retrieval.

Primary goals:
- improve downstream query context quality
- keep index updates explicit and mode-scoped
- support incremental recomputation

## Spec

### Scope

During `index` builds or refresh operations, Forge may optionally attach a short explain summary per indexed file.

Each enriched entry should include:
- `explain_summary`
- `summary_version`
- `content_hash`
- `summary_updated_at`

### Mode boundary

Only `index` workflows may persist summary enrichment.

`query` may read enriched summaries but must never write them.

### Incremental policy

Summary recomputation should occur only when:
- file content hash changed
- summary schema version changed
- explicit refresh requested

### Quality and storage constraints

- summaries must be concise and bounded
- schema versioning must allow future migration
- enrichment failures must not block base index generation

## Design

### Why this feature

Explain-enriched index metadata gives query and review modes stronger context without re-explaining everything on every run.

### Non-goals

- no hidden index mutation during read-only capabilities
- no replacement of core file-level index data
- no mandatory enrichment requirement for index success

## Definition of Done

- index schema supports optional explain summary metadata
- index build/refresh can enrich summaries incrementally
- query consumes available summaries read-only
- index works correctly with and without enrichment enabled

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 039; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
