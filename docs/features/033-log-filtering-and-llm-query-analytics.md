# Log Filtering and LLM Query Analytics

## Description

This feature adds filterable log analysis, with special support for LLM event filtering and latency bottleneck detection.

## Spec

### Scope

Add filter options to `forge logs`:
- `--run-id <id>`
- `--capability <name>`
- `--step-type llm`
- `--status failed|fallback|completed`
- `--since <iso8601>`
- `--until <iso8601>`
- `--provider <name>`
- `--model <name>`

### Analytics summaries

Add aggregate subcommands:
- `forge logs stats`
- `forge logs stats --step-type llm`
- `forge logs stats --capability query`

Metrics:
- event counts by type/status
- p50/p95 duration
- slowest steps
- fallback rate
- per-model/provider usage snapshot

### Time-finder workflow

Primary use case:
- identify time-consuming runs/steps
- identify unstable LLM calls (high fallback/latency)

### Constraints

- stats must be computed from persisted event logs only
- no mutation of run history
- unknown/invalid filters fail with clear message

## Design

### Why this feature

Users need operational answers quickly:
- where is time lost?
- which LLM calls are unstable?
- which capability path is slow?

### Non-goals

- no external BI integration
- no real-time streaming dashboard in this feature

## Definition of Done

- LLM-focused filtering works reliably
- latency and fallback analytics are available in CLI
- outputs are usable in both text and JSON modes
