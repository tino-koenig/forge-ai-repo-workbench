# Explain

## Description

Explain reads and interprets a file, symbol, or target and describes what it does.

Explain is the primary verification-oriented read capability in Forge. It is used both directly by users and internally by other workflows such as Query.

Explain must remain strictly read-only.

## Spec

### Command

- `forge explain <target>`
- optional profiles:
    - `forge explain simple <target>`
    - `forge explain detailed <target>`

### Allowed effects

- read-only
- may read related files where appropriate
- may use the index
- must not modify repository files
- may optionally write trace/cache data under `.forge/` if explicitly allowed by the system policy

### Responsibilities

- explain what a file/class/function does
- classify roles where possible:
    - entrypoint
    - implementation
    - support code
    - configuration
- identify uncertainty explicitly
- provide evidence from the code

### Profiles

#### simple
- target-focused
- no LLM required
- direct structural explanation

#### standard
- may consider related symbols/files
- stronger role classification

#### detailed
- may inspect multiple relevant files
- may use LLM to improve explanation quality
- may use multiple read passes

## Design

### Why this matters

Forge needs a strong read-only analysis primitive that later capabilities can trust.

If Query finds candidates, Explain should help determine whether a candidate actually contains the relevant logic.

### Constraints

- Explain must never fix, generate, or patch
- Explain must never become a hidden write path
- deeper profiles increase analysis depth only

## Definition of Done

- `forge explain` can explain a target file or symbol
- output includes evidence
- role classification is possible where applicable
- uncertainty is explicit
- explain remains strictly read-only