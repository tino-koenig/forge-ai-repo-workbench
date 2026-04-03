# Workstation Installation and Pipx Distribution

## Description

This feature defines the primary workstation installation model for Forge as an isolated CLI using `pipx`.

Primary goals:
- simple user installation
- isolated dependency management
- predictable updates and rollback paths

## Spec

### Scope

Define the user installation path for running Forge outside the development checkout.

Preferred workstation model:
- install Forge as an isolated CLI (`pipx install ...`)
- invoke globally as `forge ...`

### Execution expectations

- Forge must behave consistently regardless of install location.
- Repo behavior remains repository-driven (`.forge`), not machine-driven.

### Versioning policy

- workstation updates are explicit (`pipx upgrade` or reinstall)
- project behavior should remain stable via repo configuration, not client-local defaults

### Distribution policy

- `pipx` is the default user distribution target
- binary packaging is out of scope for this feature

## Design

### Why this feature

`pipx` provides clean Python CLI isolation with low user friction and aligns well with Forge's local-first repository model.

### Non-goals

- no requirement to ship native binaries
- no platform-specific installer workflow in this phase

## Definition of Done

- workstation installation instructions define `pipx` as recommended path
- global `forge` invocation is documented for user mode
- update and uninstall paths are documented
- docs explicitly state binary packaging is not part of this feature
