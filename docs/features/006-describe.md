# Describe

## Description

Describe summarizes a repository, module, or subsystem for orientation and documentation.

It is the main capability for README support, onboarding context, and structural overview.

## Spec

### Command

- `forge describe`
- `forge describe <target>`
- optional profiles:
    - `forge describe simple`
    - `forge describe detailed`

### Allowed effects

- read-only
- may use the index
- may use query and explain internally
- must not modify repository files

### Responsibilities

- summarize purpose and structure
- identify major modules or areas
- surface likely technologies/frameworks
- provide README-friendly output where useful

### Output

- concise summary
- key components
- important files or directories
- optional architecture notes
- optional README-oriented wording

## Design

### Why separate this from Query?

Query answers a question. Describe provides an oriented overview.

That difference matters for both UX and internal composition.

### Internal behavior

Describe may:
- scan repo structure
- inspect major files
- use Explain on entrypoints or important modules
- synthesize overview output

## Definition of Done

- `forge describe` produces a useful repo or target summary
- output is oriented and structured
- result is useful for README or onboarding contexts
- describe remains read-only

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 006; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
