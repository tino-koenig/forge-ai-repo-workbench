# Review

## Description

Review inspects code or repository targets using visible heuristics and project-aware rules.

Review does not fix problems. It reports findings with rationale and evidence.

## Spec

### Command

- `forge review <target>`
- optional profiles:
    - `forge review simple <target>`
    - `forge review detailed <target>`

### Allowed effects

- read-only
- may use query and explain internally
- may use the index
- must not modify repository files

### Output

Each finding should include:
- title or short label
- severity or weight if available
- evidence
- explanation
- optional recommendation

### Initial review focus

- architecture smell indicators
- controller overreach
- likely missing guards
- direct queries in the wrong layer
- visible anti-patterns
- inline styles or similar detectable patterns where relevant

## Design

### Philosophy

Review should be:
- evidence-based
- readable
- explainable
- heuristic where needed, but not vague

### Internal usage

Review may internally:
- locate related files
- explain specific targets
- apply rules to gathered evidence

### Constraints

- no automatic fixing
- no silent code changes
- avoid hand-wavy judgment without evidence

## Definition of Done

- `forge review` produces structured findings
- findings contain concrete evidence
- rules or heuristics are visible and understandable
- review remains read-only