# Log Redaction and Privacy Guards

## Description

This feature defines mandatory redaction and privacy controls for protocol logs.

Without strict guards, logs can become a security risk.

## Spec

### Scope

Apply redaction pipeline before any event write:
- remove secret values
- redact auth headers/tokens/keys
- cap raw text payload lengths
- hash sensitive identifiers where needed

### Redaction rules

Always redact:
- API keys
- Authorization headers
- bearer tokens
- known secret env var values

Default handling for prompts/content:
- store prompt template id/path
- store compact prompt hash + length
- do not store full prompt text by default

Optional debug override (explicit):
- temporary local full-prompt logging with strong warning
- auto-expire setting

### Verification

Add automated checks:
- synthetic secret injection test
- ensure secret never appears in persisted log lines

### Constraints

- redaction must be deterministic and testable
- logging must continue even if redaction skips fields
- no silent pass-through on redaction failure

## Design

### Why this feature

Operational logging must remain safe by default for real-world usage.

### Non-goals

- no full DLP engine
- no remote secrets manager integration in this feature

## Definition of Done

- redaction is enforced for all protocol log events
- secret-leak regression tests are in quality gates
- docs clearly describe what is and is not persisted

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 034; status/implemented date are tracked in `docs/status/features-index.md`.
- Protocol log redaction is enforced before event write in `core/protocol_log.py`.
- Redaction pipeline covers:
  - sensitive-key masking (`api_key`, `authorization`, `token`, `secret`, `password`, etc.)
  - bearer/auth-header pattern scrubbing in free text
  - API-key-like pattern scrubbing (`sk-...`)
  - replacement of known secret env var values in payload strings
  - bounded text length for persisted string fields
- Prompt/content handling:
  - prompt-like keys are redacted to deterministic metadata (`hash` + `length`) by default
  - optional temporary local override via `logs.protocol.allow_full_prompt_until` (ISO-8601) with warning marker
- On redaction failure, logging continues with fallback event payloads; no raw pass-through.

## How To Validate Quickly

- Synthetic probe via quality gate:
  - `python3 scripts/run_quality_gates.py` (or targeted gate execution)
- Manual spot-check:
  - run a capability to generate events
  - inspect `.forge/logs/events.jsonl`
  - verify secrets/tokens are absent and prompt hashes are present (`sha256:` marker)

## Known Limits / Notes

- Redaction is deterministic and local; it is not a full DLP engine.
- Event archives (`events-*.jsonl`) preserve already-redacted lines from active-log rotation.
