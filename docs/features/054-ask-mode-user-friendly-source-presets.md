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
- `ask:repo` -> repository-focused intent
- `ask:docs` -> framework/docs-focused intent
- `ask:latest` -> freshness-focused intent

### Relationship to query/orchestration

`ask` is a dedicated free-question mode (LLM Q&A), separate from repository retrieval.

Rules:
- `ask` does not perform repository file search by default
- `query` remains the deterministic, repository-grounded retrieval mode
- ask presets provide lightweight context intent
- web search and web retrieval are separate foundation features consumed by ask when enabled

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
- explicit ask mode metadata (preset/guided/profile)
- explicit uncertainty when no repository evidence is used

JSON output should preserve full output contract compatibility.

### Staged rollout

This feature targets a phased delivery:
1. source preset aliases (`ask:repo|docs|latest`)
2. optional guided clarification mode (`--guided`)
3. integration with independent web-search/retrieval foundations

## Design

### Why this feature

Users should be able to ask a free question quickly without entering retrieval mode. `query` remains available when grounded file-level evidence is required.

### Non-goals

- no removal of existing `query` command
- no hidden mandatory automation in first phase
- no loss of inspectability or source provenance
- no coupling ask UX spec to a specific retrieval backend implementation

## Definition of Done

- ask command and preset aliases are available
- ask mode is free-question LLM behavior (not file search)
- output explicitly states ask-mode provenance/uncertainty boundaries
- query command remains available for repository-grounded retrieval
- staged rollout path (guided, then automation) is documented

## Implemented Behavior (Current)

- Added user-facing ask entrypoints:
  - `forge ask "question"`
  - `forge ask:repo "question"`
  - `forge ask:docs "question"`
  - `forge ask:latest "question"`
- Ask commands run as dedicated free-question LLM mode (separate capability from `query`):
  - no repository file scanning by default
  - ask output contract remains structured and auditable
  - advanced ask context flags remain available (for example `--framework-profile`, `--view`)
- Preset mapping in current rollout:
  - `ask` -> generic free-question mode
  - `ask:repo` -> repository-oriented answer intent hint (no file search)
  - `ask:docs` -> docs/framework-oriented answer intent hint (no file search)
  - `ask:latest` -> freshness-oriented answer intent hint with explicit staged warning
- Web foundations are intentionally separate:
  - Feature 055 (`Web Search Foundation`)
  - Feature 056 (`Web Retrieval Foundation`)
- Ask provenance and diagnostics:
  - ask JSON includes `sections.ask` with preset/guided/profile metadata
  - ask output includes explicit uncertainty that no repository evidence anchors were used
  - ask defaults to concise text output (`compact`) unless user explicitly requests another view
- Guided mode staging:
  - `--guided` is accepted and reported as staged/not yet implemented
  - execution remains deterministic in this phase

## How To Validate Quickly

- Basic ask:
  - `forge ask "Where is query orchestration implemented?"`
- Repo/docs/latest presets:
  - `forge --view full ask:repo "Where is query orchestration implemented?"`
  - `forge --view full ask:docs --framework-profile typo3-v14 "TYPO3 routing docs"`
  - `forge --output-format json ask:latest "latest TYPO3 docs"`
- Verify JSON contract:
  - inspect `sections.ask`
  - inspect `sections.llm_usage`
  - inspect uncertainty warnings for no-retrieval and staged latest behavior

## Known Limits / Notes

- `ask:latest` does not execute web retrieval in this phase; it returns model-only output with explicit warning.
- `ask:docs` and `ask:repo` are intent presets in this phase and do not trigger repository search.
- Guided clarification (`--guided`) is reserved for a later staged rollout.
