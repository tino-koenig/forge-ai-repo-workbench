# Development Installation and Invocation Model

## Description

This feature defines the recommended Forge setup and invocation model for Forge core development.

Primary goals:
- fast development iteration
- explicit, reproducible local execution
- no dependency on global Python state

## Spec

### Scope

Define the developer path for running Forge from a checkout.

Recommended workflow:
1. create a dedicated virtual environment for the Forge checkout
2. install Forge in editable mode (`pip install -e .`)
3. invoke via `forge ...` console entrypoint from that environment

### Invocation behavior

The development command surface should prefer:
- `forge <mode> ...`

`python -m forge ...` remains supported as a compatibility path, but is not the primary developer UX.

### Optional repo wrapper

A repository-local wrapper may be provided to reduce activation friction.

If provided, wrapper requirements are:
- argument passthrough without semantic changes
- clear failure when local environment is missing
- no hidden writes or side effects

### Non-goals in this phase

- no binary packaging target
- no global installer as primary dev path

## Design

### Why this feature

Forge development needs a stable and quick local loop. Editable install inside a dedicated venv gives immediate code feedback while keeping environments isolated.

## Definition of Done

- developer setup docs define dedicated venv + editable install as default
- `forge ...` is documented as the primary dev invocation
- compatibility invocation via `python -m forge ...` is documented
- optional wrapper behavior is explicitly constrained
