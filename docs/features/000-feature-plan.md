# Forge Feature Plan

## Goal

Forge is a transparent, composable AI-assisted repo tool.

The first public phase should focus on strong, understandable read-oriented capabilities and only then expand into controlled write workflows.

## Prioritized features

1. Core CLI & Capability Model
2. Index
3. Query
4. Explain
5. Review
6. Describe
7. Test Drafting

## Why this order?

- The core model defines how Forge behaves.
- Index improves speed and structure without becoming mandatory.
- Query and Explain form the backbone for later higher-level flows.
- Review and Describe build directly on top of Query/Explain.
- Test Drafting is the first controlled generation feature built on the same foundations.

## Out of scope for this phase

- autonomous fixing
- feature implementation
- issue resolution
- platform-driven workflows
- heavy configuration systems
- broad natural-language command parsing

## Design rule

Each feature should be:
- directly callable by the user
- reusable by other Forge workflows
- explicit about its allowed effects
- understandable in isolation