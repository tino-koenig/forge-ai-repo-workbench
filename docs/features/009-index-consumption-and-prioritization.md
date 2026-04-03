# Index Consumption And Prioritization

## Description

This feature makes practical index usage first-class across analysis capabilities.

The index must remain optional, but when present it should improve speed, candidate quality, and path prioritization.

## Spec

### Scope

Extend index consumption for:
- review
- test drafting
- describe (deeper structural usage)
- query/explain (strengthen existing usage)

### Usage goals

When index is available:
- prioritize preferred paths
- de-prioritize low-priority paths
- avoid expensive scans where index data is sufficient
- use indexed symbols/metadata to improve candidate selection

When index is missing:
- continue to work fully with direct repo scanning
- produce comparable output quality where feasible
- clearly indicate fallback mode

### Priority semantics

Index path classes should influence scoring, not hard-code final decisions:
- preferred: boost
- normal: neutral
- low_priority: reduce weight
- index_exclude/hard_ignore: excluded from indexed workflows unless explicitly required

## Design

### Why this matters

Feature 002 is only valuable if other capabilities consume it consistently.

This feature turns the index from passive artifact into an active, transparent optimization layer.

### Constraints

- index must not become mandatory
- no hidden capability behavior changes
- weighting must stay inspectable and explainable

## Definition of Done

- review and test use index metadata in candidate/rule targeting
- describe uses index structure for component summaries when available
- query/explain index usage is consistent with shared scoring semantics
- all affected capabilities have explicit index fallback paths
- outputs indicate whether index-assisted mode was used
