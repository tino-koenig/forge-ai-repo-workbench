# Central Orchestration Foundation for Modes

## Description

Extract orchestration runtime from mode-local query logic into a central reusable core foundation.

Goals:
- make orchestration available across modes
- reduce duplicated state-machine logic in mode modules
- preserve explicit, auditable behavior

## Addresses Issues

- [Issue 22 - Query Orchestration Loop Is Not a Central Reusable System](/Users/tino/PhpstormProjects/forge/docs/issues/22-query-orchestration-loop-is-not-a-central-reusable-system.md)

## Spec

### Central runtime

- Add a core orchestration engine that handles:
  - bounded iteration lifecycle
  - budget accounting
  - done-reason transitions
  - progress tracking and stop criteria
  - iteration trace accumulation

### Mode adapter contract

- Modes provide:
  - action catalog
  - deterministic handler implementations
  - mode policy boundaries
  - mode-specific sections serialization
- Engine remains mode-agnostic.

### Migration scope

- First migrate query to the central engine.
- Add one additional mode using the same engine to validate reusability.

## Definition of Done

- Query orchestration loop is no longer primarily implemented inline in `modes/query.py`.
- Shared engine lives under `core` with stable adapter contracts.
- Existing query orchestration output structure remains backward-compatible.

## Implemented Behavior (Current)

- Added central orchestration foundation in `core/mode_orchestrator.py` with bounded cycle/wall-time accounting via `iter_bounded_cycles`.
- `modes/query.py` now consumes the central cycle engine for orchestration lifecycle control instead of maintaining its own raw time/range loop.
- `modes/explain.py` also consumes the same foundation for bounded related-file orchestration, validating cross-mode reuse.
- Query `action_orchestration` output contract remains backward-compatible.

## How To Validate Quickly

- Run:
  - `python3 forge.py --llm-provider mock --output-format json query "compute_price"`
- Verify:
  - `sections.action_orchestration` is present and valid
  - done reason remains in expected contract set (`sufficient_evidence`, `budget_exhausted`, `policy_blocked`, `no_progress`)
- Reuse gate:
  - `PYTHONPATH=. python3 -c "import shutil,tempfile; from pathlib import Path; from scripts.run_quality_gates import FIXTURE_BASIC_SRC, gate_central_mode_orchestrator_foundation; td=tempfile.TemporaryDirectory(prefix='forge-gate-'); repo=Path(td.name)/'repo'; shutil.copytree(FIXTURE_BASIC_SRC, repo); gate_central_mode_orchestrator_foundation(repo); print('ok')"`

## Known Limits / Notes

- Action handler semantics remain mode-local; this feature centralizes bounded orchestration lifecycle and timing control.
