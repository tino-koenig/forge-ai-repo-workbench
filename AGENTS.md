

# AGENTS.md

## Project

Forge is a transparent, composable AI-assisted repo tool for understanding, reviewing, testing, documenting, and improving code.

Forge is built around explicit modes, visible tool usage, and understandable workflows. It should remain useful in small, focused tasks without relying on hidden automation.

Core idea:
- with control, not magic

## Product direction

Forge is not meant to be a vague "run an agent" shell.

It should evolve as a repo-first workbench with explicit modes such as:
- query
- review
- test
- describe
- later: fix
- later: implement
- later: issue

Advanced workflows must be built from the same understandable foundations as the basic ones.

## Priorities

1. Keep the architecture explicit and easy to inspect.
2. Prefer small, composable building blocks over hidden orchestration.
3. Keep the core useful without heavy configuration.
4. Make outputs understandable and auditable by humans.
5. Preserve a clear separation between core functionality and optional sharpening through profiles, rules, or templates.

## Principles

### Explicit over implicit
Forge should prefer clear modes, visible steps, and predictable behavior over hidden automation.

### Composable, not magical
Complex workflows should be built from simple, understandable parts.

### AI where it helps
AI should be used for interpretation, summarization, prioritization, and proposal generation — not to hide core logic.

### Human-auditable by default
Results should be grounded in file paths, matches, findings, commands, or generated artifacts that a human can inspect.

### Local-first, repo-first
Forge should work directly against a real repository and remain useful without platform lock-in.

### Configuration sharpens, it does not define
Profiles, rules, templates, and overrides should refine behavior, not become the center of the product.

## Current scope

Primary public v1 focus:
- query
- review
- describe
- test drafting

Later workflows:
- fix
- implement
- issue-driven flows

Do not prematurely optimize for full autonomy.

## Implementation guidance

### Architecture
- Prefer a clear, boring architecture over clever abstraction.
- Keep modules focused and small.
- Avoid hidden control flow where possible.
- Make it easy to understand how a mode works from reading the code.

### CLI design
- Prefer explicit subcommands such as `forge query`, `forge review`, `forge test`, `forge describe`.
- Do not make a generic `run everything` style command the primary interface.
- Keep command behavior predictable and mode-specific.

### Tools
- Build strong foundational tools first.
- Basic tools should remain useful on their own.
- Favor transparent tool pipelines such as search → read → analyze → answer.
- Avoid turning core functionality into an opaque agent loop too early.

### Configuration and profiles
- Keep default behavior useful with little or no configuration.
- Add profiles and overrides only where they clearly sharpen repo understanding or workflow quality.
- Do not let configuration complexity become the product.
- Repo- or user-specific conventions should be configurable, not hardcoded.

### Review and analysis
- Review results should contain concrete evidence.
- Prefer findings with file paths, snippets, or rationale over vague judgments.
- Heuristics are acceptable, but they should be visible and explainable.

### Test support
- Start with test drafting and test planning before ambitious autonomous test workflows.
- Respect existing test conventions in a repository when possible.
- Prefer grounded test generation over generic boilerplate.

### Fixes and implementation
- Later fix and implementation flows must build on the same explicit foundation.
- Avoid introducing a separate black-box "agent mode" that bypasses the architecture.
- Changes should remain inspectable and understandable.

## Non-goals

Forge should not become:
- a configuration-first framework
- a generic autonomous agent shell
- a prompt box with hidden behavior
- a platform-specific product at its core

## Working style for coding agents

When working in this repository:
- preserve explicitness
- preserve clarity over cleverness
- avoid unnecessary framework layers
- avoid introducing hidden automation
- prefer readable code and straightforward control flow
- keep future extensibility, but do not overengineer

When adding new functionality:
1. keep the user-facing mode clear
2. keep the internal tool flow understandable
3. keep the implementation easy to inspect
4. keep the defaults useful
5. keep configuration optional and secondary

## Definition of success

A successful Forge change should make the project:
- more understandable
- more composable
- more useful for real repo work
- more transparent in behavior
- easier to extend without becoming magical

## Short reminder

Forge is a transparent repo tool with AI assistance.
It should help with real repository work from analysis to implementation.
It should remain understandable by humans at every stage.

**With control, not magic.**