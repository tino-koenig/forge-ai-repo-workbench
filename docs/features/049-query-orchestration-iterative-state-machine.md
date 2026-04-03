# Query Orchestration Iterative State Machine

## Description

This feature upgrades query orchestration from a single decision pass to a bounded multi-iteration state machine.

Primary goals:
- execute orchestration decisions as a real loop
- make each iteration explicit and inspectable
- preserve strict budget and policy boundaries

## Spec

### Scope

Introduce a canonical query loop state and iterate until stop conditions are met.

Required state fields:
- question and planner context
- candidate set and ranking snapshot
- evidence payload
- iteration counter
- budget usage (`tokens`, `files`, `wall_time_ms`)
- source usage (`repo_hits`, `framework_hits`, optional `external_hits`)
- source-aware budget usage (`repo_files_read`, `framework_files_read`)
- last decision and done reason

### Loop protocol

Each iteration must follow:
1. decision request (`continue|stop` + `next_action`)
2. policy and schema validation
3. action execution
4. state update
5. stop evaluation

Source-aware execution policy is optional in this feature phase.  
Initial implementation focuses on bounded iterative execution independent of source-expansion policy.

### Termination

Loop must terminate with one explicit `done_reason`:
- `sufficient_evidence`
- `budget_exhausted`
- `policy_blocked`
- `no_progress`

### Guardrails

- max iterations must be enforced at runtime
- no hidden extra iterations beyond configured bounds
- invalid decisions must route to deterministic fallback and terminate safely

## Design

### Why this feature

Current orchestration quality is limited when only one decision cycle is executed. A bounded state machine allows controlled adaptive retrieval without losing transparency.

### Non-goals

- no unbounded autonomous loop
- no write actions in query mode

## Definition of Done

- query orchestration executes multiple iterations when needed
- state transitions are explicit and logged per iteration
- done reasons are deterministic and reproducible
- budget and policy bounds are enforced in every iteration

## Implemented Behavior (Current)

- Query orchestration now runs as a bounded loop up to `llm.query_orchestrator.max_iterations`.
- Each iteration evaluates decision -> validates -> executes action -> updates state -> checks stop conditions.
- Runtime stop reasons are explicit and propagated:
  - `sufficient_evidence`
  - `budget_exhausted`
  - `policy_blocked`
  - `no_progress`
- Runtime budgets are enforced per run/iteration:
  - wall time (`max_wall_time_ms`)
  - files read (`max_files`)
  - token budget approximation (`max_tokens`)
- Iteration traces are emitted in output contract under `sections.action_orchestration.iterations`.

## How To Validate Quickly

- Run full view query and inspect orchestration block:
  - `forge --view full query "Where is X defined?"`
- Run JSON query and inspect iterative trace:
  - `forge --output-format json query "Where is X defined?"`
  - verify `sections.action_orchestration.iterations[]` and `done_reason`
- Tune bounds in `.forge/config.toml` (`llm.query_orchestrator.*`) and verify loop behavior changes accordingly.

## Known Limits / Notes

- Current loop executes a conservative subset of actions effectively (`read`, `explain`, `rank`, `summarize`).
- `search` expansion remains intentionally minimal in this phase.
- Token budget tracking is approximate (bounded estimator), not provider token accounting.
