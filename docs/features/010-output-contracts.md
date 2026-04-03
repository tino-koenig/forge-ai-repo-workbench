# Output Contracts

## Description

This feature defines canonical output contracts for Forge capabilities to improve auditability, composability, and machine-readability.

Each capability keeps its domain-specific content while following a consistent structural contract.

## Spec

### Contract fields

All capability outputs should support a common structure:
- summary
- evidence
- uncertainty
- next_step

Capability-specific sections may be added, for example:
- query: likely_locations
- explain: role_classification
- review: findings
- describe: key_components
- test: proposed_test_cases

### Modes

- human-readable default output (current CLI style)
- optional structured output mode (e.g. JSON)

### Requirements

- evidence must include concrete file references where possible
- uncertainty must be explicit when inference is weak
- next_step should be actionable and capability-appropriate

## Design

### Why this matters

Consistent contracts make cross-capability composition reliable and easier to test.

They also make output quality and regressions more measurable.

### Constraints

- do not flatten all capabilities into generic text
- preserve explicit capability identity
- avoid opaque score-only output without evidence

## Definition of Done

- canonical output contract is documented centrally
- all v1 capabilities map to the contract
- optional structured output mode exists for at least query/explain/review
- evidence and uncertainty sections are consistently present
- existing human-readable output remains understandable

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 010; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
