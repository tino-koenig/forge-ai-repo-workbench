# Redacted LLM Observability

## Description

This feature adds explicit, safe observability for LLM invocation paths.

Forge should make LLM runtime behavior debuggable without leaking secrets
or dumping sensitive prompt payloads by default.

## Spec

### Scope

Introduce optional observability output for LLM calls:
- invocation metadata
- timing and status
- fallback reasons
- source-of-config attribution

### Output channels

Initial channels:
- structured JSON fields in capability output (already partially present)
- optional local diagnostics log file under `.forge/logs/` when enabled

### Redaction rules

Must never log:
- API keys
- Authorization headers
- raw full prompt text by default
- raw repository file contents beyond existing evidence exposure

Allowed metadata:
- provider
- model
- base URL (non-secret)
- timeout/budget values
- profile/template identifiers
- request duration and status

### Controls

Config controls (explicit):
- observability enabled/disabled
- log level (`minimal`, `standard`, `debug`)
- retention count/size guardrails

Default:
- minimal metadata in output contracts
- no persistent log files unless explicitly enabled

## Design

### Why this feature

As provider integration grows, debugging failures needs traceability.
Observability must remain compatible with Forge transparency and safety goals.

### Non-goals

- no full prompt transcript storage by default
- no centralized telemetry backend in this feature

## Definition of Done

- LLM invocation metadata is consistently available and redacted
- optional local logging is configurable and safe by default
- secret leakage checks are added to quality gates
- fallback diagnostics become easier to interpret in local workflows

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 017; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
