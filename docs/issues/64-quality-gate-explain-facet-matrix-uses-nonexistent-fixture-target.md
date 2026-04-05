# Quality Gate Explain Facet Matrix Uses Nonexistent Fixture Target

## Problem

`gate_explain_facet_quality_matrix` executes on the `basic_repo` fixture but uses
`core/llm_observability.py` as target.

That file does not exist in the fixture, so explain resolves no target and the
facet alias checks fail with messages such as:
- `explain facet matrix (settings): alias focus mismatch`

## Scope

- keep the explain facet alias/flag parity checks unchanged.
- use a target path that exists in `tests/fixtures/basic_repo`.

## Acceptance Criteria

- `gate_explain_facet_quality_matrix` passes deterministically in isolated runs and CI.
- gate still validates alias and `--focus` parity for `settings/defaults/llm/outputs/symbols`.

## Resolution Notes

- switched matrix target from `core/llm_observability.py` to `src/service.py`
  (present in the `basic_repo` fixture).
