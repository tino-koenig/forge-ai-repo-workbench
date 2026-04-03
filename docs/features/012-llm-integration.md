# LLM Integration

## Description

This feature adds controlled LLM support to Forge capabilities where interpretation quality benefits from model assistance.

LLM usage must remain explicit, auditable, and bounded by capability effect policies.

## Spec

### Scope

Introduce optional LLM-assisted steps for:
- query (summary and prioritization refinement)
- explain (clarity and role interpretation refinement)
- review (finding phrasing and rationale synthesis)
- describe (overview wording and onboarding summaries)
- test drafting (case phrasing and skeleton quality)

Indexing and effect policy enforcement remain non-LLM core logic.

### Core rules

- LLM is assistive, not authoritative
- evidence must remain grounded in repository artifacts
- outputs must distinguish evidence from inference
- capabilities must keep working without LLM
- no capability may expand its allowed effects due to LLM use

### Invocation policy

Per capability/profile, define whether LLM is:
- off
- optional
- preferred

Initial recommendation:
- simple: off
- standard: optional
- detailed: optional or preferred depending on capability

### Provider and model policy

- provider/model selection is explicit and configurable
- model usage is logged in execution metadata
- defaults should be conservative and cost-aware
- capability behavior must not depend on hidden user-global prompts

### Prompting constraints

- prompts must include explicit task boundaries
- prompts must request evidence-backed responses
- prompts must include no-write constraints for read-only capabilities
- prompt templates are versioned and inspectable in-repo

### Fallback behavior

On LLM unavailability or failure:
- continue with deterministic heuristic path
- report fallback mode explicitly
- never fail silently

### Safety and transparency

- include an LLM usage section in output when LLM was used
- show whether statements are evidence-derived or inferred
- avoid fabricated file references or symbols
- include uncertainty notes where confidence is limited

## Design

### Why now

After shared primitives, index consumption, output contracts, and quality gates are in place, LLM integration can be added without losing control or auditability.

### Non-goals

- no autonomous fix/implement behavior
- no hidden multi-step agent loop
- no replacement of deterministic evidence collection

### Internal integration shape

Recommended flow:
1. deterministic evidence collection
2. optional LLM interpretation/synthesis
3. contract-conform output assembly
4. uncertainty and provenance annotation

## Definition of Done

- LLM integration exists behind explicit capability/profile policy
- each LLM-assisted capability still works without LLM
- outputs include provenance (evidence vs inference) and LLM usage status
- prompt templates are in-repo, versioned, and reviewable
- quality gates cover both LLM and no-LLM paths
- effect boundaries remain enforced regardless of model usage
