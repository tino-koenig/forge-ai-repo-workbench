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
