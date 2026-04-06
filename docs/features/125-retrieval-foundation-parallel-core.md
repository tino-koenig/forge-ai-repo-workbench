# Retrieval Foundation Parallel Core Bootstrap

## Description

Implement Foundation 07 as a new parallel core retrieval foundation with structured request/outcome contracts, source-transparent candidate/evidence provenance, deterministic deduplication, and explicit budget/policy diagnostics.

## Spec

- Add models:
  - `RetrievalRequest`
  - `RetrievalCandidate`
  - `RetrievalEvidence`
  - `RetrievalOutcome`
  - `RetrievalDiagnostic`
- Add core API:
  - `run_retrieval(request, context) -> RetrievalOutcome`
- Keep retrieval responsibilities scoped to:
  - source selection
  - candidate generation
  - evidence collection
  - deduplication
- Keep retrieval separate from ranking and target resolution.
- Enforce explicit source policy and budget behavior with structured diagnostics.

## Definition of Done

- Foundation module exists at `core/retrieval_foundation.py`.
- Request/Outcome contracts are typed and deterministic.
- Provenance is preserved across candidates/evidence, including dedupe merges.
- Status contract (`ok|partial|blocked|error`) is explicit and test-covered.
- Nondeterministic sources are explicitly marked.
- Unit tests cover deterministic behavior for equal input.

## Implemented Behavior (Current)

- Added parallel retrieval core with:
  - structured query-term signals (`QueryTermSignal`)
  - explicit request contracts (`target_scope`, `source_scope`, `budget_view`, `policy_context`)
  - source adapter/context contracts for deterministic fixture-style retrieval execution
- Implemented deterministic retrieval pipeline:
  - source selection (policy/scope/budget-aware)
  - candidate generation
  - evidence generation
  - candidate/evidence deduplication with provenance retention
  - budget truncation diagnostics
- Added explicit diagnostics for:
  - policy/source blocks
  - nondeterministic source usage/blocks
  - deduplication
  - budget truncation
- Added integration context fields for future foundations:
  - `workspace_snapshot_id`
  - `run_id`
  - `trace_id`

## How To Validate Quickly

1. Run `python3 -m unittest tests/test_retrieval_foundation.py`.
2. Verify:
   - request/outcome shape
   - source provenance on candidates/evidence
   - dedupe provenance preservation
   - status transitions (`ok|partial|blocked|error`)
   - policy and budget diagnostics
   - deterministic repeated outputs

## Known Limits / Notes

- This foundation intentionally avoids ranking, resolver behavior, and mode-specific logic.
- Current source adapters are contract-level and deterministic; advanced source-specific retrieval algorithms are deferred to later phases.
