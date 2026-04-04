# Ask and Web Foundations Lack Regression Quality Gates

## Problem

No quality gates or tests currently target ask command behavior and web foundation integration.

Observed behavior:
- `scripts/run_quality_gates.py` contains no `ask`/web-search/web-retrieval gates.
- Current regressions can ship without automated detection (policy gating, provenance, preset divergence).

## Required behavior

- Add explicit ask/web integration gates and focused test fixtures.
- Cover success, fallback, policy-blocked, and no-network scenarios.

## Done criteria

- Quality gate suite includes ask/web checks.
- Core ask preset contracts and provenance fields are asserted in CI.
- Deterministic no-network path is validated without brittle external dependencies.

## Linked Features

- [075-ask-and-web-quality-gates.md](/Users/tino/PhpstormProjects/forge/docs/features/075-ask-and-web-quality-gates.md)

## Implemented Behavior (Current)

- Ask/web regression gates were added and integrated into `run_all_gates`.
- Coverage now includes:
  - policy-blocked path (`access.web=false`),
  - docs/latest freshness divergence,
  - provenance source typing,
  - ask/query routing boundary contract,
  - deterministic no-network provider-failure fallback.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Confirm these gates pass:
  - `gate_ask_web_access_policy`
  - `gate_ask_latest_freshness_policy`
  - `gate_ask_source_aware_provenance`
  - `gate_ask_query_boundary_cleanup`
  - `gate_ask_no_network_fallback`

## Known Limits / Notes

- No-network validation uses local proxy blocking to avoid flaky dependence on external connectivity.
