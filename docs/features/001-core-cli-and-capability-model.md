# Core CLI & Capability Model

## Description

This feature defines the foundational execution model of Forge.

Forge is built around explicit capabilities such as `query`, `explain`, `review`, `describe`, and `test`. These capabilities are directly callable by the user and may also be used internally by other Forge workflows.

The model must preserve:
- explicitness
- composability
- strict effect boundaries
- predictable behavior

## Spec

### Core concepts

Forge commands are defined by:

- capability
- profile
- target or question
- allowed effects

### Initial capabilities

- query
- explain
- review
- describe
- test

### Initial profiles

- simple
- standard
- detailed

### Effect classes

- read_only
- forge_write
- repo_write
- command_exec

### Initial rules

- `query`, `explain`, `review`, `describe` are read-only
- `index` may write to `.forge/`
- no capability may silently escalate its effects
- internal reuse of capabilities must not weaken effect boundaries

### CLI shape

Primary form:
- `forge query ...`
- `forge explain ...`
- `forge review ...`
- `forge describe ...`
- `forge test ...`

Optional profile use:
- `forge query simple ...`
- `forge explain detailed ...`

## Design

### Why this exists

Many AI tools blur intent and effects. Forge must not.

A user asking for explanation or review must never trigger fixes or repo modifications.

### Internal structure

Recommended internal representation:

- capability
- profile
- input payload
- effect policy

Capabilities should be implemented as reusable internal functions/services, while the CLI remains a thin layer on top.

### Constraints

- no hidden "agent run everything" primary mode
- no implicit write behavior
- no profile may change allowed effects

## Definition of Done

- Forge has a canonical internal command model
- capabilities and profiles are defined centrally
- effect classes are documented and enforced
- read-only capabilities cannot write to the repo
- CLI commands map cleanly to internal capabilities