# Adaptive Query Retrieval with Explain Feedback

## Description

This feature upgrades `forge query` retrieval quality by using `explain` as an explicit reranking and continuation signal.

Primary goals:
- improve relevance of returned files
- make continuation decisions evidence-based
- preserve read-only behavior

## Spec

### Scope

`query` flow becomes:
1. deterministic candidate search
2. `explain` on top candidates
3. evidence-based rerank
4. LLM decision: stop or inspect additional candidates (bounded)
5. synthesis with explicit evidence references

### Explain-assisted ranking

For each explained candidate, derive structured relevance signals, for example:
- question-to-file intent match
- concrete evidence density
- confidence of inferred linkage

Ranking must cite file paths and signal rationale.

### Continuation strategy

When confidence is below threshold, `query` may analyze additional candidates in the next iteration.

Continuation must respect global budgets and stop conditions from orchestration policy.

### Output requirements

Default output should include:
- top matching files
- short why-it-matches explanation
- uncertainty note when confidence is low
- optional next investigation suggestion

## Design

### Why this feature

Search-only ranking often misses semantically relevant files. Explain-guided reranking increases quality without hiding how decisions were made.

### Non-goals

- no write behavior in `query`
- no opaque relevance scores without rationale
- no mandatory deep analysis for every query

## Definition of Done

- `query` uses explain-derived signals for reranking
- low-confidence queries trigger bounded continuation when useful
- outputs include explicit evidence-based rationale
- regression fixtures show improved top-result relevance on difficult queries

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 038; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
