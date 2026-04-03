# LLM-Assisted Step Protocol and Event Model

## Description

This feature defines a canonical step protocol for Forge workflows with explicit LLM participation.

Goal:
- LLM can contribute where useful
- LLM does not own the entire flow
- every step remains inspectable and auditable

## Spec

### Scope

Define a shared event model for capability execution steps:
- deterministic preprocessing
- optional LLM step(s)
- deterministic postprocessing
- output assembly

### Step principles

- each step has explicit input/output boundaries
- each step declares whether it is deterministic or LLM-assisted
- each step records start/end timestamps and status
- each step records fallback behavior when applicable

### Event schema (canonical)

Required fields:
- `event_id`
- `run_id`
- `timestamp`
- `capability`
- `step_name`
- `step_type` (`deterministic|llm|io|policy`)
- `status` (`started|completed|failed|fallback`)
- `duration_ms` (when completed/failed/fallback)
- `metadata` (bounded structured object)

### LLM step metadata

When step_type = `llm`, include:
- provider/model
- prompt template id/path
- prompt profile
- token/cost fields when available
- fallback reason if not completed successfully

### Constraints

- no secret material in metadata
- no unbounded raw prompt dumps by default
- step protocol must not change capability effect boundaries

## Design

### Why this feature

It creates the foundation for meaningful protocol logging and debugging while preserving Forge's explicit architecture.

### Non-goals

- no hidden orchestration engine
- no automatic behavior changes based on logs

## Definition of Done

- event schema is defined centrally
- all core capabilities can emit protocol-compliant events
- step metadata is sufficient to reconstruct execution flow per run
