# Protocol Log Storage (JSONL First)

## Description

This feature introduces persistent protocol logging for run events using JSONL as first storage backend.

Decision:
- start with JSONL
- keep event schema stable
- enable optional SQLite indexing later without changing event semantics

## Spec

### Scope

Store protocol events in:
- `.forge/logs/events.jsonl`

Each line = one event object conforming to feature 030 schema.

### Why JSONL first

- append-only and easy to reason about
- simple debugging with standard tools
- no migration complexity at initial stage
- low implementation risk

### Rotation and retention

Configurable controls:
- max file size
- max event age days
- max events count

Rotation behavior:
- rotate to timestamped archive file
- preserve valid JSONL lines

### Optional indexing path

Future optional enhancement:
- build SQLite index from JSONL for fast filter queries
- JSONL remains source-of-truth in this phase

### Constraints

- logging failures must not fail core capability execution
- logs must be best-effort with explicit warning events
- sensitive values redacted before write

## Design

### Why this feature

It provides practical observability quickly while keeping architecture simple and transparent.

### Non-goals

- no mandatory SQLite dependency in first phase
- no remote log aggregation in this feature

## Definition of Done

- protocol events are persisted in JSONL per run
- rotation/retention controls exist and are test-covered
- logs are readable without custom tooling

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 031; status/implemented date are tracked in `docs/status/features-index.md`.
- Protocol events are persisted in JSONL at:
  - `.forge/logs/events.jsonl`
- Persisted lines use the canonical feature-030 event schema.
- Storage is best-effort and does not alter capability execution behavior.
- Rotation and retention are configurable via `.forge/config.toml`:
  - `logs.protocol.max_file_size_bytes`
  - `logs.protocol.max_event_age_days`
  - `logs.protocol.max_events_count`
- When rotation threshold is exceeded, active log rotates to timestamped archive:
  - `.forge/logs/events-<UTC_TIMESTAMP>.jsonl`

## How To Validate Quickly

- Configure small limits:
  - set `[logs.protocol]` in `.forge/config.toml`
- Execute several runs:
  - `forge --llm-provider mock query "compute_price"`
- Verify:
  - `.forge/logs/events.jsonl` exists and contains JSONL event lines
  - rotated archives appear when size threshold is crossed (`events-*.jsonl`)
  - active `events.jsonl` remains bounded by count/age rules

## Known Limits / Notes

- This feature stores events in local JSONL only; optional SQLite indexing remains a later enhancement.
- Retention is applied to active log content; archives preserve rotated history for manual inspection.
