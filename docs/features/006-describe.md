# Describe

## Description

Describe summarizes a repository, module, or subsystem for orientation and documentation.

It is the main capability for README support, onboarding context, and structural overview.

## Spec

### Command

- `forge describe`
- `forge describe <target>`
- optional profiles:
    - `forge describe simple`
    - `forge describe detailed`

### Allowed effects

- read-only
- may use the index
- may use query and explain internally
- must not modify repository files

### Responsibilities

- summarize purpose and structure
- identify major modules or areas
- surface likely technologies/frameworks
- provide README-friendly output where useful

### Output

- concise summary
- key components
- important files or directories
- optional architecture notes
- optional README-oriented wording

## Design

### Why separate this from Query?

Query answers a question. Describe provides an oriented overview.

That difference matters for both UX and internal composition.

### Internal behavior

Describe may:
- scan repo structure
- inspect major files
- use Explain on entrypoints or important modules
- synthesize overview output

## Definition of Done

- `forge describe` produces a useful repo or target summary
- output is oriented and structured
- result is useful for README or onboarding contexts
- describe remains read-only