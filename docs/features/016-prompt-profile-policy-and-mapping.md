# Prompt Profile Policy and Mapping

## Description

This feature formalizes prompt profile behavior for LLM-assisted paths.

Prompt profiles must be explicit, capability-aware, and validated.
They must never introduce hidden behavior or effect escalation.

## Spec

### Scope

Define and enforce:
- prompt profile registry
- capability-to-profile mapping rules
- validation for configured profile values

Initial profiles:
- `strict_read_only`
- `review_strict`
- `describe_onboarding`

### Mapping rules

- profiles are selected explicitly from config/CLI policy context
- capabilities may define allowed profile subset
- invalid profile selections fail validation with actionable diagnostics

### Capability defaults

Initial default mapping:
- query -> `strict_read_only`
- explain -> `strict_read_only`
- review -> `review_strict`
- describe -> `describe_onboarding`
- test -> `strict_read_only`

### Transparency requirements

Output metadata must include:
- selected prompt profile
- template path used
- config source for profile resolution

### Safety constraints

- no free-form inline system/developer role text
- no runtime role-chain assembly from unbounded user strings
- profile selection must not alter capability effect boundaries

## Design

### Why this feature

Feature 013 introduced config-driven prompt controls.
Feature 016 ensures those controls stay constrained and predictable.

### Non-goals

- no prompt marketplace/plugin system
- no per-user hidden profile overrides

## Definition of Done

- profile registry is centralized and validated
- capability defaults and allowed mappings are enforced
- invalid profile usage is surfaced via `doctor` and runtime metadata
- quality gates cover valid and invalid profile resolution paths
