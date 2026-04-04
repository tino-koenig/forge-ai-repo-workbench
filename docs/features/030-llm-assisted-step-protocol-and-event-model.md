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

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 030; status/implemented date are tracked in `docs/status/features-index.md`.
- Canonical protocol schema is centralized in `core/step_protocol.py` via `build_step_event(...)` and event normalization.
- Run history now stores protocol events under:
  - `execution.protocol_events` in `.forge/runs.jsonl`
- Every capability run (except `runs` self-inspection command, which does not append history) emits baseline protocol steps:
  - `deterministic_preprocessing` (`started`, `completed`)
  - `capability_execution` (`started`, `completed|failed`)
  - `output_assembly` (`started`, `completed`)
- LLM-assisted steps are emitted as explicit `step_type=llm` events when usage metadata is present:
  - `summary_refinement`
  - `query_planner`
  - `query_action_orchestrator`
- LLM metadata includes provider/model/template/profile and token/cost/fallback fields when available.

## How To Validate Quickly

- Run a capability:
  - `forge query "where is compute_price defined?"`
- Inspect latest run record:
  - `forge --output-format json runs last`
- Validate:
  - `execution.protocol_events` exists
  - each event contains: `event_id`, `run_id`, `timestamp`, `capability`, `step_name`, `step_type`, `status`, `metadata`
  - terminal statuses (`completed|failed|fallback`) include `duration_ms`

## Known Limits / Notes

- Protocol events are persisted in run history and (with feature 031) mirrored to `.forge/logs/events.jsonl`.
- Step durations are measured around CLI/runtime boundaries and usage-reported LLM latency where available.
- Metadata is sanitized and bounded; raw prompts/secrets are not included.
