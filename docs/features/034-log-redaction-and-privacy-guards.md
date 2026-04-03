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
