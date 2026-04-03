# LLM Foundation

## Description

This feature defines a reusable LLM foundation layer for Forge capabilities and workflows.

Primary goals:
- centralize LLM provider/runtime behavior in one inspectable layer
- enforce consistent safety, policy, and observability rules
- decouple mode logic (`ask`, `query`, `explain`, `review`, later `fix`) from provider specifics

## Spec

### Scope

Provide shared primitives for all LLM-enabled features:
- provider abstraction and request execution
- prompt rendering and prompt-profile policy
- capability/profile policy gating (`off` / `optional` / `preferred`)
- bounded context assembly and output limits
- structured fallback and error handling
- usage/provenance/observability metadata

### Foundation APIs

Expose stable, mode-agnostic interfaces such as:
- `resolve_settings(...)`
- `render_prompt(...)` / template resolution
- `complete(...)` for provider calls
- `run_llm_step(...)` with policy and fallback handling
- normalized outcome object (`summary`, `usage`, `uncertainty`)

Mode features must consume these APIs and avoid duplicating provider logic.

### Policy and safety

Required controls:
- capability/profile invocation policy matrix
- timeout, token, and budget ceilings
- provider and config validation before invocation
- no hidden mode escalation through prompt path
- explicit fallback reasons in contract output

### Prompt and profile model

Foundation owns:
- prompt template loading
- prompt-profile allowlist/default mapping per capability
- system-template resolution
- language/output-style controls

Mode features own:
- task-specific prompt input payload
- interpretation of returned text into mode contract sections

### Observability and provenance

Foundation must emit structured usage data:
- attempted/used/fallback state
- provider/model/base_url (where applicable)
- latency and budget signals
- prompt profile/system template provenance

Logs and contract metadata must be human-auditable and redaction-safe.

### Provider support model

Initial required providers:
- `mock`
- `openai_compatible`

Provider extensions must be additive and isolated behind foundation interfaces.

### Failure and fallback contract

On failure, foundation must:
- return deterministic fallback output to caller
- include machine-readable fallback reason
- avoid throwing mode-breaking exceptions for expected provider/runtime errors

## Design

### Why this feature

Without a dedicated foundation, LLM behavior spreads across modes and becomes inconsistent, harder to verify, and expensive to evolve. A shared foundation keeps modes small, explicit, and composable.

### Non-goals

- no opaque autonomous agent loop
- no mode-specific business logic in foundation
- no removal of deterministic non-LLM mode behavior
- no hard dependency that forces every mode to use LLM

## Definition of Done

- foundation API boundary is documented and implemented
- all current LLM-using modes call foundation interfaces (no duplicated provider code)
- policy, prompt-profile, and fallback behavior are consistent across modes
- usage/provenance metadata is emitted uniformly in contracts/logs
- provider additions require no mode-level refactor

## Dependency Notes

This foundation is a prerequisite for:
- ask web-assisted synthesis flows
- future edit/fix foundations requiring LLM planning or patch reasoning
- consistent multi-step orchestration across capabilities
