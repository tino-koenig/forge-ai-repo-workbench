# Run History Always JSON Contract

## Description

This feature makes run history consistently machine-processable by persisting a structured JSON contract for every capability run, independent of selected CLI output view.

Primary goals:
- reliable run-to-run reuse (`--from-run`, chained workflows)
- stable automation and tooling integration
- no ambiguity between human output rendering and stored execution result

## Spec

### Scope

For every non-`runs` capability execution, `.forge/runs.jsonl` must contain:
- request metadata
- execution metadata
- structured contract payload (`output.contract`) as canonical result
- optional text output (`output.text`) as rendered view artifact

`output.contract` becomes mandatory for new records.

### Contract persistence behavior

Rules:
1. Contract generation is capability-internal and always produced.
2. JSON output mode prints that contract directly.
3. Text output mode still prints human-first output, but the same run record stores the full contract.
4. History consumers (`--from-run`, analytics, replay metadata) rely on `output.contract`, not text parsing.

### Backward compatibility

Existing history entries without contract remain readable, but are considered legacy:
- do not break list/show behavior
- `--from-run` on legacy entries should fail clearly with migration guidance

Optional later migration command can backfill legacy records.

### Safety and constraints

- no hidden behavior change in capability effects
- no loss of current human-readable terminal output
- no contract omission based on `--view` or `--output-format`

## Design

### Why this feature

Run history is now part of Forge composition semantics. If contracts are optional, follow-up workflows become fragile and format-dependent. Mandatory contract persistence keeps workflows deterministic and auditable.

### Non-goals

- no automatic semantic reconstruction of old text-only runs in this feature
- no schema redesign of existing output contract fields

## Definition of Done

- all newly written run records include `output.contract`
- `--from-run` works equally for runs created in text and JSON output modes
- legacy text-only runs fail with explicit actionable message (not silent fallback)
- quality gates verify contract persistence across output modes
