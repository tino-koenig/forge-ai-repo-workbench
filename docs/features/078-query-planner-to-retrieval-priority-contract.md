# Query Planner-to-Retrieval Priority Contract

## Description

Define a strict transfer contract from planner priorities to deterministic retrieval weighting.

Goals:
- preserve planner intent ordering in retrieval
- prevent generic terms from dominating anchor terms
- keep planner output interpretable and auditable

## Addresses Issues

- [Issue 21 - Query Planner Term Ordering Can Overweight Generic Terms](/Users/tino/PhpstormProjects/forge/docs/issues/21-query-planner-term-ordering-can-overweight-generic-terms.md)

## Spec

### Priority mapping

- Retrieval weighting must be driven by planner priority buckets first:
  - lead terms (anchor)
  - support terms (qualifier)
  - fallback search terms
- If `search_terms` order conflicts with lead/support priority, lead/support takes precedence in effective weighting.

### Deterministic safeguards

- Generic classifier terms (`where`, `code`, `location`, `function`, `module`, etc.) cannot outweigh concrete lead terms.
- Planner output normalization must enforce stable ordering and dedup semantics.

### Observability

- Query output should expose effective weighted term order used for retrieval.

## Definition of Done

- Effective retrieval order visibly places concrete anchor terms first for locate-definition queries.
- Generic terms remain supportive and cannot outrank exact identifier signals.
- Quality gates validate planner-to-retrieval mapping.

## Implemented Behavior (Current)

- Query now exposes planner-to-retrieval transfer explicitly via:
  - `sections.query_planner.effective_retrieval_terms`
  - `sections.query_planner.effective_term_weights`
- Effective retrieval terms are composed in deterministic priority order:
  - lead terms
  - support terms
  - planner search terms (deduplicated append)
- Weighting remains position-based, but now auditable against planner priority output.

## How To Validate Quickly

- Run:
  - `python3 forge.py --llm-provider mock --output-format json --view full query "Wo ist enrich_detailed_context definiert?"`
- Verify:
  - `sections.query_planner.lead_terms[0] == "enrich_detailed_context"`
  - `sections.query_planner.effective_retrieval_terms[0] == "enrich_detailed_context"`
  - first `effective_term_weights` item has the highest weight
- Gate check:
  - `PYTHONPATH=. python3 -c "import shutil,tempfile; from pathlib import Path; from scripts.run_quality_gates import FIXTURE_BASIC_SRC, gate_query_planner_priority_transfer; td=tempfile.TemporaryDirectory(prefix='forge-gate-'); repo=Path(td.name)/'repo'; shutil.copytree(FIXTURE_BASIC_SRC, repo); gate_query_planner_priority_transfer(repo); print('ok')"`

## Known Limits / Notes

- Planner quality still depends on model output quality; this feature guarantees deterministic priority transfer and observability, not perfect semantic term generation.
