# Test Drafting

## Description

Test Drafting derives test ideas, test plans, or draft test code from real repository context.

In the first phase, this feature should focus on grounded drafting rather than ambitious autonomous test generation.

## Spec

### Command

- `forge test <target>`
- optional profiles:
    - `forge test simple <target>`
    - `forge test detailed <target>`

### Allowed effects

Initial phase:
- read-only
- may analyze existing tests
- may use query and explain internally
- may use the index

Later phase:
- may optionally write draft test files or patches under controlled write workflows

### Responsibilities

- find existing test conventions
- identify likely target behavior
- derive relevant cases
- include explicit requested cases where provided
- produce test plans or draft test output

### Initial output

- likely test location
- relevant existing test conventions
- proposed test cases
- optional draft test skeleton

## Design

### Why keep this conservative first?

Test generation can easily become generic boilerplate if not grounded in the repo.

Forge should first prove that it can:
- understand the target
- respect project test conventions
- derive useful cases

### Internal composition

Test Drafting may use:
- Query to locate relevant files
- Explain to understand the target
- Describe or index data to understand project testing structure

## Definition of Done

- `forge test` can analyze a target and propose test cases
- existing test conventions are considered where available
- output is grounded in real repository context
- the initial version remains read-only unless explicitly expanded later

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 007; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
