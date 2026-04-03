# Forge Init Team Templates and Interactive Onboarding

## Description

This feature defines `forge init` as the first-run setup flow for repository-level Forge configuration.

Primary goals:
- intuitive first-run experience
- team-specific template bootstrap
- repository-owned, versioned Forge configuration

## Spec

### Scope

`forge init` initializes Forge in a target repository by creating `.forge/` configuration artifacts.

Init should support both:
- interactive onboarding (`forge init`)
- deterministic non-interactive setup (`forge init --template <name> --non-interactive`)

### Template model

Templates represent opinionated team or project defaults.

Template responsibilities:
- generate concrete `.forge/` files
- encode profile/rule defaults for repository workflows
- include template identity/version metadata for traceability

### Interactive question design

First-run questions must be deliberately minimal and high-impact.

Requirements:
- short guided flow
- recommended defaults visible at each step
- only ask questions that change generated config meaningfully
- preview of created/changed files before write

### Git and repository ownership

Generated core configuration files are intended to be committed to repository git.

Init output should distinguish:
- repository-owned artifacts (commit)
- local/runtime artifacts (do not commit)

### Safety behavior

- if `.forge/` already exists, init must not overwrite silently
- explicit confirmation or force flag required for replacement behavior

## Design

### Why this feature

`forge init` is the product entrypoint. Strong onboarding quality and explicit generated artifacts are critical for team adoption and reproducibility.

### Non-goals

- no hidden cloud bootstrap process
- no mandatory interactive-only flow
- no secret collection in committed repo files

## Definition of Done

- `forge init` supports interactive and non-interactive modes
- team templates can generate repository-owned `.forge/` config
- interactive flow is concise, default-guided, and preview-first
- docs clearly define which init outputs belong in git
