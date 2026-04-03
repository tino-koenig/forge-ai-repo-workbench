# LLM Query Planner

## Description

This feature adds a controlled LLM query-planning step to improve retrieval quality and output usefulness.

Primary goals:
- normalize user questions to concise English intent
- remove filler words
- generate high-signal search terms and code-like variants

## Spec

### Scope

Enhance `forge query` with an optional planner stage before deterministic retrieval:
1. user question input
2. optional LLM planner (single prompt)
3. bounded term set + deterministic retrieval
4. optional rerank/synthesis as already defined

### Prompt model

Initial implementation uses one versioned planner prompt template in-repo.

Planner output fields:
- `normalized_question_en`
- `intent`
- `lead_terms`
- `support_terms`
- `search_terms`
- `code_variants`
- `dropped_filler_terms`

Constraints:
- fixed JSON schema output
- bounded list sizes
- no file/symbol fabrication claims
- no hidden write suggestions

### Why one prompt first

Yes, this should start as one prompt.
Reason:
- simpler to validate
- lower latency/cost than multi-step prompting
- easier to debug and tune

Possible later split (not in this feature):
- separate translation and term-expansion prompts if quality data justifies complexity

### Configuration

Add planner config under `.forge/config.toml`:
- `llm.query_planner.enabled`
- `llm.query_planner.mode` (`off|optional|preferred`)
- `llm.query_planner.max_terms`
- `llm.query_planner.max_code_variants`
- `llm.query_planner.max_latency_ms`

### Fallback behavior

If planner fails or exceeds bounds:
- fallback to deterministic term derivation
- emit explicit fallback reason
- continue query execution

### Output quality requirements

Human-first text output (standard view) should show:
- concise interpreted question (if planner used)
- top likely locations
- short why/evidence summary
- next step

Avoid overwhelming users with metadata in default view.
Detailed planner diagnostics remain in full view/JSON.

## Design

### Why this feature

Users need output that is truly supportive for real questions, especially cross-language phrasing.
Planner quality is required for practical adoption.

### Non-goals

- no mandatory planner dependency for query
- no replacement of deterministic retrieval core
- no hidden autonomous workflows
- no token/cost accounting in this feature

## Definition of Done

- single in-repo planner prompt is integrated for query
- planner improves term quality on multilingual and conceptual query fixtures
- default text output stays human-first and concise
- quality gates cover:
  - planner success path
  - planner fallback path

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 028; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.
- Planner output now supports prioritized buckets:
  - `lead_terms`: core anchor terms
  - `support_terms`: qualifying/context terms
- Runtime normalization demotes generic taxonomy/location terms (for example `code`, `location`, `file`, `module`) from `lead_terms` into `support_terms`.
- Query retrieval consumes planner buckets in stable order (`lead_terms`, then `support_terms`, then `search_terms`) with deduplication.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
