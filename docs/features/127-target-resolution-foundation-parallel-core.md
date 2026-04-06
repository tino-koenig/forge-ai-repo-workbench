# Target Resolution Foundation Parallel Core Bootstrap

## Description

Implement Foundation 09 as a new parallel core target-resolution foundation with deterministic path/symbol/from-run resolution, explicit ambiguity handling, transition validation, and structured resolution provenance.

## Spec

- Add models:
  - `TargetRequest`
  - `TargetCandidate`
  - `TargetResolutionResult`
  - `TransitionDecision`
  - `TargetResolutionDiagnostic`
- Add core APIs:
  - `resolve_target(request, context) -> TargetResolutionResult`
  - `resolve_from_run_reference(request, context) -> TargetResolutionResult`
  - `order_target_candidates_for_resolution(candidates, policy) -> list[TargetCandidate]`
  - `validate_transition(source_mode, target_mode, context) -> TransitionDecision`
- Keep explicit contracts for:
  - resolved target representation (`resolved_target`)
  - fallback/heuristic visibility
  - ambiguity top-k transparency
  - from-run transition provenance

## Definition of Done

- Foundation module exists at `core/target_resolution_foundation.py`.
- Path/symbol/fallback/from-run resolution is deterministic and test-covered.
- Ambiguity is explicit (no hidden best-guess).
- Transition validation blocks invalid mode handoffs with structured diagnostics.
- Unit tests cover ordering determinism, status semantics, and provenance fields.

## Implemented Behavior (Current)

- Added deterministic resolver pipeline with priority order:
  1. explicit valid path
  2. from-run reference (if set)
  3. symbol candidates
  4. policy fallback (directory/repo)
- Added explicit ambiguity behavior:
  - `resolution_status=ambiguous`
  - candidate list + `ambiguity_top_k`
- Added from-run resolution with transition validation and structured transition metadata.
- Added policy switch for unresolved explicit path fallback behavior.

## How To Validate Quickly

1. Run `python3 -m unittest tests/test_target_resolution_foundation.py`.
2. Verify:
   - explicit path resolution
   - ambiguous symbol behavior with top-k
   - fallback visibility
   - from-run transition allow/block behavior
   - deterministic candidate ordering

## Known Limits / Notes

- This foundation does not perform retrieval or ranking itself.
- Multi-target bundle semantics from V2 are intentionally deferred.
- Resolver is intentionally parallel and not yet integrated into active mode pipelines.
