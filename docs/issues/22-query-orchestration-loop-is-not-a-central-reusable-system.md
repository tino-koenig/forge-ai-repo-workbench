# Query Orchestration Loop Is Not a Central Reusable System

## Problem

The orchestration state machine and action-handler execution are largely embedded in `modes/query.py`.
This prevents reuse by other modes and duplicates orchestration concerns in mode code.

## Evidence

- `modes/query.py` contains:
  - iterative loop control
  - budget accounting
  - anti-stall overrides
  - handler execution (`search/read/explain/rank/summarize/stop`)
  - progress scoring application
  - iteration trace assembly
- `core/llm_integration.py` only returns decisions; orchestration runtime is not shared as a mode-agnostic engine.

## Required behavior

- Orchestration runtime must be a central reusable system in `core`.
- Modes should provide only mode-specific handlers/adapters and deterministic policy boundaries.
- Shared tracing, budgeting, progress policy, and done-reason mechanics should be unified.

## Done criteria

- Query uses a central orchestration engine (not mode-local loop as primary implementation).
- At least one additional mode can reuse the same orchestration foundation with mode-specific actions.
- Existing query orchestration output contract remains compatible.

## Linked Features

- [Feature 079 - Central Orchestration Foundation for Modes](/Users/tino/PhpstormProjects/forge/docs/features/079-central-orchestration-foundation-for-modes.md)

## Implemented Behavior (Current)

- Bounded orchestration lifecycle control was extracted into `core/mode_orchestrator.py`.
- Query now uses the central cycle engine for iteration and wall-time accounting.
- Explain also uses the same central orchestration foundation (bounded related-file orchestration path), demonstrating multi-mode reuse.

## How To Validate Quickly

- `python3 forge.py --llm-provider mock --output-format json query "compute_price"`
- Ensure `sections.action_orchestration` remains present and contract-compatible.
- Run gate:
  - `PYTHONPATH=. python3 -c "import shutil,tempfile; from pathlib import Path; from scripts.run_quality_gates import FIXTURE_BASIC_SRC, gate_central_mode_orchestrator_foundation; td=tempfile.TemporaryDirectory(prefix='forge-gate-'); repo=Path(td.name)/'repo'; shutil.copytree(FIXTURE_BASIC_SRC, repo); gate_central_mode_orchestrator_foundation(repo); print('ok')"`

## Known Limits / Notes

- Handler execution logic is still mode-specific by design; centralized behavior covers bounded orchestration mechanics.
