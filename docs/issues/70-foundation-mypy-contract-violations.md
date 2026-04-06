

# Foundation Type Contracts Are Violated and Not Yet Enforced by a Static Type Gate

## Problem

Several implemented foundation modules currently violate their declared static type contracts.
The runtime test suite passes, but `mypy` still reports real contract mismatches across core foundation files.

This means the foundation layer is functionally usable, but not yet type-safe enough to serve as a hardened architectural contract.

## Why this matters

Forge foundations are intended to be explicit, stable contracts between layers.
If type mismatches remain unresolved:

- cross-foundation interfaces become softer than intended,
- invalid assumptions can survive runtime tests,
- refactors become riskier,
- developer trust in the foundation layer decreases.

A passing runtime suite is not sufficient if the static contract surface is still inconsistent.

## Evidence

A current `mypy` run on implemented foundation files reports multiple errors across several modules, including for example:

- `core/target_resolution_foundation.py`
- `core/runtime_settings_foundation_registry.py`
- `core/mode_execution_foundation.py`
- `core/retrieval_foundation.py`
- `core/runtime_settings_foundation.py`

Current result:

- **20 errors**
- across **5 files**

These are not documentation issues, but real type-contract violations in implemented foundation code.

## Required behavior

- All implemented foundation modules must pass `mypy` cleanly.
- Type contracts between implemented foundations must be explicit and internally consistent.
- Foundation quality must not rely on runtime tests alone where static typing can express the same contract more safely.
- Type checking for implemented foundations must become a repeatable quality gate.

## Done criteria

- `mypy` reports **0 errors** for all implemented foundation files.
- No known type ignores or workarounds hide unresolved contract mismatches without explicit justification.
- A documented and repeatable type-check command exists for implemented foundations.
- Static type checking is integrated as a quality gate for the implemented foundation set.

## Scope

This issue is about the **implemented foundation modules** only.
It does not require immediate type cleanup of unrelated non-foundation modules.

## Implemented Behavior (Current)

- Implemented foundation modules pass `mypy` with `0 errors` for the defined foundation file set.
- `scripts/run_quality_gates.py` includes a dedicated gate: `gate_foundation_mypy_contracts`.
- The gate resolves an available `mypy` runner deterministically (`.venv/bin/python -m mypy`, `sys.executable -m mypy`, or `mypy` binary) and fails clearly if none is available.
- A regression test (`tests/test_foundation_mypy_contracts.py`) enforces that the implemented foundation file set stays `mypy`-clean.

## Suggested implementation direction

- Fix the current reported violations first.
- Define the exact set of implemented foundation files that must always pass `mypy`.
- Add a dedicated quality-gate command for that set.
- Keep the gate narrow and deterministic before expanding it later.

## How To Validate Quickly

1. Run the dedicated quality gate:
   - `python3 scripts/run_quality_gates.py --only gate_foundation_mypy_contracts`
2. Run the direct foundation type-check command:
   - `.venv/bin/python -m mypy core/mode_execution_foundation.py core/runtime_settings_foundation.py core/runtime_settings_foundation_registry.py core/workspace_foundation.py core/workspace_locators.py core/workspace_scope_rules.py core/workspace_roles.py core/output_contract_foundation.py core/observability_foundation.py core/orchestration_foundation.py core/retrieval_foundation.py core/evidence_ranking_foundation.py core/target_resolution_foundation.py`
3. Confirm that the result is `0 errors`.
4. Re-run the existing runtime test suite to ensure no behavioral regressions were introduced.

## Known Limits / Notes

- The overall repository may still contain non-foundation areas outside the initial static type gate.
- This issue is focused on making the implemented foundation core statically trustworthy first.
