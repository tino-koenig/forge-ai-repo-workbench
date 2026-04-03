# Ask Mode with User-Friendly Source Presets

## Description

This feature introduces `ask` as a user-first query entrypoint with simple source presets.

Primary goals:
- reduce command complexity for everyday users
- keep advanced orchestration controls available behind the scenes
- make source selection explicit but lightweight

## Spec

### Scope

Add simplified ask command forms:
- `forge ask "question"`
- `forge ask:repo "question"`
- `forge ask:docs "question"`
- `forge ask:latest "question"`

Preset intent:
- `ask:repo` -> repository-focused retrieval
- `ask:docs` -> framework/docs-focused retrieval (optionally profile-aware)
- `ask:latest` -> web retrieval with freshness checks and citations

### Relationship to query/orchestration

`ask` is a UX layer on top of the existing query/orchestration core.

Rules:
- preserve deterministic core behavior and policies
- map presets to source-scope defaults and retrieval budgets
- keep advanced options available for orchestration and power users

### Profile integration

When `frameworks.toml` is available, `ask` may use:
- profile aliases
- default docs profiles
- framework version defaults

Optional usage:
- `forge ask:docs "..." --profile typo3-v14`

### Output behavior

Ask output should remain concise by default and include:
- direct answer summary
- top likely locations/sources
- concise source provenance (`source_type`)
- citations for docs/web sources

JSON output should preserve full output contract compatibility.

### Staged rollout

This feature targets a phased delivery:
1. source preset aliases (`ask:repo|docs|latest`)
2. optional guided clarification mode (`--guided`)
3. later automation-assisted source selection

## Design

### Why this feature

Users should not need to manage many source flags for common questions. Presets offer clear defaults while the orchestration layer still has rich controls for complex retrieval.

### Non-goals

- no removal of existing `query` command
- no hidden mandatory automation in first phase
- no loss of inspectability or source provenance

## Definition of Done

- ask command and preset aliases are available
- preset-to-source mapping is explicit and documented
- output includes concise provenance and citations where applicable
- advanced orchestration options remain available
- staged rollout path (guided, then automation) is documented
