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
