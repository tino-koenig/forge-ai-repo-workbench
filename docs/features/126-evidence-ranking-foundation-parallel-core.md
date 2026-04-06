# Evidence Ranking Foundation Parallel Core Bootstrap

## Description

Implement Foundation 08 as a new parallel core ranking foundation that deterministically ranks retrieval candidates/evidence with explicit score components, stable tie-break rules, visible policy versioning, and explainable outcomes.

## Spec

- Add models:
  - `RankedCandidate`
  - `ScoreComponent`
  - `RankingPolicy`
  - `RankingOutcome`
  - `RankingDiagnostic`
  - `TieBreakDecision`
- Add core API:
  - `rank_evidence(request, retrieval_outcome, context) -> RankingOutcome`
- Keep ranking flow separated into explicit steps:
  - component computation
  - score aggregation
  - tie-break application
  - optional declared rerank diagnostics/component path
- Keep strict boundary:
  - no retrieval
  - no target resolution
  - no mode-specific branching

## Definition of Done

- Foundation module exists in `core/evidence_ranking_foundation.py`.
- Ranking policy id/version and component weights are explicit and test-covered.
- Ranked candidates expose score components and explanations.
- Tie-break remains deterministic and visible.
- Optional rerank path is declared and diagnostic-visible (not hidden replacement logic).
- Unit tests cover deterministic behavior and status/diagnostic handling.

## Implemented Behavior (Current)

- Added deterministic ranking core with typed policy/request/context/contracts.
- Added explicit score components for:
  - retrieval raw score
  - evidence count
  - term coverage
  - source determinism
  - optional rerank locator-term match
- Added deterministic tie-break pipeline with visible tie-break decisions.
- Added short structured explanation strings per ranked candidate.
- Added optional rerank diagnostics (`rerank_applied`, `rerank_disabled_by_policy`).

## How To Validate Quickly

1. Run `python3 -m unittest tests/test_evidence_ranking_foundation.py`.
2. Verify:
   - deterministic rank order
   - explicit component IDs and weighted contributions
   - stable tie-break
   - visible policy id/version
   - rerank diagnostics and no hidden component substitution

## Known Limits / Notes

- This foundation intentionally does not fetch data (Foundation 07 responsibility).
- This foundation intentionally does not resolve final targets (later foundations).
- Component sets and weight defaults are contract-level defaults and can be extended later via explicit policy versions.
