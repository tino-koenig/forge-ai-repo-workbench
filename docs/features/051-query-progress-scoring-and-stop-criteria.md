# Query Progress Scoring and Stop Criteria

## Description

This feature introduces explicit progress scoring to decide whether additional orchestration iterations are useful.

Primary goals:
- avoid low-value extra iterations
- stop confidently when evidence quality is sufficient
- make continuation decisions measurable

## Spec

### Scope

Define a deterministic progress score computed after each iteration.

Progress signals may include:
- new high-signal candidate paths in top results
- improved top confidence/linkage confidence
- increased evidence quality and coverage
- reduced ambiguity in summary intent alignment
- source-aware quality gain (repo evidence gain weighted higher than framework-only drift)

### No-progress policy

If progress remains below threshold for configurable consecutive iterations, orchestration must stop with `done_reason = no_progress`.

### Budget interplay

Progress scoring must work together with hard budgets:
- even high progress cannot bypass budget ceilings
- low progress should stop before exhausting budgets where appropriate
- framework-only progress should not keep loop alive indefinitely when repo confidence is already sufficient

### Output and trace

Query output should expose concise progress context in full diagnostic views:
- per-iteration progress score
- stop trigger (sufficient evidence, no progress, or budget)
- source contribution breakdown (repo/framework)

## Design

### Why this feature

Bounded loops still need quality-aware stopping to avoid wasted latency and token cost. Progress scoring provides predictable, inspectable continuation logic.

### Non-goals

- no opaque black-box stopping heuristic
- no LLM-only stopping decision without deterministic checks
- no source-agnostic scoring that over-rewards huge framework candidate churn

## Definition of Done

- deterministic progress score is computed per iteration
- no-progress stopping is implemented and tested
- done_reason selection reflects progress and budget outcomes
- full diagnostics include progress and stop rationale
- progress scoring documents how source type influences stop decisions

## Implemented Behavior (Current)

- Query orchestration computes a deterministic progress score after each executable iteration via:
  - top-result churn (`new_top_paths`)
  - confidence uplift (`confidence_gain`)
  - evidence growth (`evidence_gain`)
  - repo-signal uplift (`repo_gain`)
  - framework-only drift penalty (`framework_drift_penalty`)
- A progress threshold gate is enforced:
  - default `threshold = 1.5`
  - iterations below threshold increment a `no_progress_streak`
  - after `no_progress_streak_limit = 2`, orchestration stops with `done_reason = no_progress`
- Progress diagnostics are emitted in query output:
  - per-iteration `progress_score`
  - per-iteration `progress_passed`
  - per-iteration `progress_components`
  - orchestration-level `progress_policy` configuration block

## How To Validate Quickly

- Full text diagnostics:
  - `forge --view full query "Where is query orchestration implemented?"`
  - inspect `Action Orchestration` for per-iteration `progress=...` and component breakdown
- JSON diagnostics:
  - `forge --output-format json query "Where is query orchestration implemented?"`
  - inspect `sections.action_orchestration.progress_policy`
  - inspect `sections.action_orchestration.iterations[].progress_score`
  - inspect `sections.action_orchestration.iterations[].progress_components`

## Known Limits / Notes

- Current progress weights and threshold are static constants; no profile-specific tuning yet.
- Progress is based on deterministic retrieval and explain heuristics, not semantic quality scoring from LLM output.
- Under orchestrator fallback/error paths, progress fields are still present but can remain zeroed/empty by design.
