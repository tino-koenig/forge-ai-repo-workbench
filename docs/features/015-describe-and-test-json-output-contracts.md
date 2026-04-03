# Describe and Test JSON Output Contracts

## Description

This feature extends canonical JSON output contracts to:
- `describe`
- `test`

Both capabilities already provide structured information in text form.
This feature makes them machine-consumable and contract-consistent with:
- `query`
- `explain`
- `review`
- `doctor`

## Spec

### Scope

Add `--output-format json` support for:
- `forge describe`
- `forge test`

### Contract requirements

Both capabilities must emit:
- `capability`
- `profile`
- `summary`
- `evidence`
- `uncertainty`
- `next_step`

And capability-specific `sections`.

### Describe sections

`describe` JSON should include:
- target metadata (`kind`, resolved target path when available)
- key components
- technologies (languages/framework hints)
- architecture notes (where available)
- LLM usage and provenance (if integrated path is active)

### Test sections

`test` JSON should include:
- resolved target metadata
- inferred test conventions
- proposed test cases
- suggested test location
- optional draft skeleton
- LLM usage and provenance (if integrated path is active)

### Behavior constraints

- no change in read-only effect boundaries
- text output remains unchanged in spirit
- JSON output must be deterministic for no-LLM path given same inputs

## Design

### Why this feature

Forge now has multiple capabilities useful for automation.
Without JSON contracts for `describe` and `test`, orchestration quality is uneven.

### Non-goals

- no schema versioning system in this feature
- no additional generation behavior

## Definition of Done

- `describe` and `test` support JSON contracts
- contracts include required base fields and capability sections
- quality gates validate contract shape for both capabilities
- no regressions in existing text output behavior
