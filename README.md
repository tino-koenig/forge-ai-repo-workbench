# Forge

**Forge is a transparent, composable AI-assisted repo tool for understanding, reviewing, testing, documenting, and improving code.**

Forge is built for developers who want useful AI support without opaque automation.

It focuses on explicit modes and clear building blocks instead of hidden agent behavior:
- query a repository
- review code and structures
- draft tests
- describe a codebase
- support targeted fixes and implementations

Forge is designed to be useful in small, focused tasks first. More advanced workflows are built from the same visible, understandable foundations.

**With control, not magic.**

## Why Forge?

Most AI coding tools fall into one of two categories:
- lightweight assistants for snippets and chat
- opaque agents that do a lot, but hide too much

Forge takes a different approach.

It treats repository work as a set of explicit, composable tasks:
- find and explain
- inspect and review
- draft and verify
- fix and implement

The goal is not maximum automation at any cost.  
The goal is useful, transparent assistance for real repository work.

## Principles

- **Explicit over implicit**  
  Forge prefers clear modes and visible steps over hidden automation.

- **Composable, not magical**  
  Complex workflows should be built from understandable pieces.

- **AI where it helps**  
  AI is used for interpretation, summarization, prioritization, and proposal generation — not to hide core logic.

- **Human-auditable by default**  
  Outputs should be inspectable and grounded in files, paths, commands, and findings.

- **Local-first, repo-first**  
  Forge should work directly against a real repository and remain useful without platform lock-in.

- **Configuration sharpens, it does not define**  
  Configuration should refine behavior, not become the product.

## Core modes

### `forge query`
Answer targeted questions about a repository.

Examples:
- Where are addresses imported?
- Show all occurrences of inline styles.
- Which files are involved in sending emails?
- Where is field `foo` written?

### `forge review`
Review code, files, or structures using explicit heuristics and project-aware rules.

Examples:
- Does this controller contain business logic?
- Are controller actions properly guarded?
- Are there direct queries in the wrong layer?

### `forge test`
Draft or generate tests from real code context.

Examples:
- Write tests for class `PriceCalculator`.
- Cover the edge case where the amount is negative.
- Show missing test cases for parser `X`.

### `forge describe`
Summarize a repository, module, or subsystem for orientation and documentation.

Examples:
- Summarize this repository for a README.
- Describe the architecture.
- Explain the import flow.

### Later modes
- `forge fix`
- `forge implement`
- `forge issue`

These build on the same foundations rather than introducing a separate black-box agent.

## Example commands

```bash
forge query "Where are addresses imported?"
forge review src/Controller/UserController.php
forge test src/Service/PriceCalculator.php --case "negative amount"
forge describe
```


## Design goals

Forge should be:

- useful without heavy configuration
- predictable in behavior
- modular in implementation
- understandable in output
- adaptable through simple profiles and overrides

Forge should not be:

- a prompt box with hidden behavior
- a configuration-first framework
- a fully autonomous coding black box

## Configuration

Forge supports optional profiles, rules, and local overrides.

These are meant to sharpen repository understanding, review behavior, and templates — not to replace sensible defaults.

Examples:
- prefer certain source paths
- add framework-specific review rules
- define test conventions
- point to a local reference repository

## Status

Forge is in early development.

The first public focus is:
- query
- review
- describe
- test drafting

Fix and implementation workflows come next, built on the same transparent foundations.

## Vision

Forge aims to become a reliable workbench for AI-assisted repository work:

- understand codebases
- review and inspect structures
- draft tests and documentation
- support targeted changes
- eventually help resolve issues in a controlled, inspectable way

The long-term goal is not an opaque autonomous agent.  
It is a reliable, understandable workbench for AI-assisted repository work.

**With control, not magic.**