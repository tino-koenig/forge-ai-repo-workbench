# Ask and Web Quality Gates

## Description

Add dedicated quality gates for ask mode and web foundations.

Goals:
- prevent silent regressions in ask preset behavior,
- enforce policy/provenance/fallback contracts,
- keep external dependency behavior deterministic in CI.

## Spec

### Gate coverage

Include checks for:
- ask preset routing and contract sections
- access policy blocked-path handling
- web search/retrieval fallback semantics under no-network or provider errors
- provenance correctness for web evidence
- `ask:docs` vs `ask:latest` behavior divergence

### Test strategy

- use deterministic fixtures/mocks for web layers where possible
- avoid brittle reliance on live internet responses in gate suite

## Definition of Done

- Quality gate suite includes ask/web gates.
- CI catches contract and policy regressions for ask presets.
- Gate logs provide actionable failure diagnostics.

## Addresses Issues

- [18-ask-and-web-foundations-lack-regression-quality-gates.md](/Users/tino/PhpstormProjects/forge/docs/issues/18-ask-and-web-foundations-lack-regression-quality-gates.md)

## Implemented Behavior (Current)

- Added dedicated ask/web gate coverage in `scripts/run_quality_gates.py`:
  - `gate_ask_web_access_policy`
  - `gate_ask_latest_freshness_policy`
  - `gate_ask_source_aware_provenance`
  - `gate_ask_query_boundary_cleanup`
  - `gate_ask_no_network_fallback`
- The gate suite now validates:
  - preset/routing contracts,
  - policy-blocked behavior (`access.web=false`),
  - docs/latest divergence,
  - source-aware provenance,
  - deterministic no-network/provider-failure fallback semantics.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify ask/web gate names above pass in the quality-gate output stream.

## Known Limits / Notes

- The no-network regression path is enforced via deterministic proxy blocking (`127.0.0.1:9`) to avoid brittle reliance on live internet responses.
