# Log Viewer and Run-Focused Inspection

## Description

This feature adds a first-class CLI log viewer for protocol events.

Users can inspect logs for:
- a specific run
- a capability
- recent timeline slices

## Spec

### Scope

Add command family:
- `forge logs tail`
- `forge logs run <run_id>`
- `forge logs show <event_id>`

Views:
- text (human-first)
- json (`--output-format json`)

### Run-focused behavior

`forge logs run <run_id>` should:
- show ordered step timeline
- include status and duration per step
- highlight failed/fallback steps
- provide summary totals (duration, llm step count, fallback count)

### Human-first output

Default text should prioritize:
1. timeline overview
2. problematic steps
3. next diagnostic hint

Detailed metadata available via full/detail view.

### Constraints

- viewer is read-only
- missing run id gives explicit actionable message

## Design

### Why this feature

Protocol logging is only useful if users can inspect it quickly during real troubleshooting.

### Non-goals

- no GUI viewer in this phase

## Definition of Done

- log viewer commands exist and are documented
- run-focused view is chronological and useful for debugging
- JSON output supports automation
