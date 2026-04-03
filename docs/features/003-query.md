# Query

## Description

The Query feature answers targeted questions about a repository by finding and prioritizing relevant locations.

Query is not the final authority on meaning. Its job is to:
- understand the question enough to search effectively
- gather candidates
- collect evidence
- surface likely next steps

Where needed, Query may internally use Explain for verification, but it remains a read-only capability.

## Spec

### Command

- `forge query <question>`
- optional profiles:
    - `forge query simple <question>`
    - `forge query detailed <question>`

### Allowed effects

- read-only
- may use the index if present
- may call read-only internal capabilities such as `explain`
- must not modify repository files

### Initial behavior

- extract or normalize search terms
- search the repository
- group and rank matches
- surface likely candidate files
- present evidence

### Output structure

- short answer or summary
- likely locations
- evidence
- optional next step

### Profiles

#### simple
- no LLM required
- basic search and grouping
- limited interpretation

#### standard
- better grouping and ranking
- may use index
- may produce a more structured answer

#### detailed
- may inspect top candidates more deeply
- may use `explain`
- may use LLM for summary only if allowed

## Design

### Core philosophy

Query should answer:
- where to look
- what is likely relevant
- what evidence supports that

It should not overclaim certainty without verification.

### Internal composition

Possible internal sequence:
- normalize question
- derive search terms
- search
- group by file
- score candidates
- optionally verify top candidates via Explain
- summarize

## Definition of Done

- `forge query` works on a real repo
- returns evidence-backed candidate files
- output distinguishes between raw matches and likely locations
- read-only constraints are preserved
- profiles change depth, not effects

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 003; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
