# OpenAI-Compatible Provider + Config TOML

## Description

This feature adds a concrete provider adapter for Forge LLM calls:
- `openai_compatible`

The provider is designed to work with:
- OpenAI-compatible endpoints
- LiteLLM gateways
- OpenAI-compatible vLLM endpoints (without adding a dedicated vLLM provider)

Configuration is moved to a repo-local TOML file:
- `.forge/config.toml`

Secrets remain out of repo config and are resolved from environment variables (for example via `.env` loading in local workflows).

## Spec

### Scope

Add explicit provider wiring for:
- query
- explain
- review
- describe
- test

The provider only handles model invocation and response extraction.
Capability effect boundaries, evidence collection, and policy enforcement remain unchanged.

### Provider decision

Chosen provider model:
- Forge provider name: `openai_compatible`

Why:
- one explicit, stable integration surface
- compatible with LiteLLM as routing layer
- avoids provider-specific branching in Forge core

### Configuration location and precedence

Primary configuration file:
- `.forge/config.toml`

Precedence (highest to lowest):
1. CLI flags
2. environment variables
3. `.forge/config.toml`
4. safe defaults

### Config schema (initial)

Example:

```toml
[llm]
provider = "openai_compatible"

[llm.openai_compatible]
base_url = "http://localhost:4000/v1"
model = "gpt-4o-mini"
api_key_env = "FORGE_LLM_API_KEY"
timeout_s = 30

[llm.request]
context_budget_tokens = 12000
max_output_tokens = 700
temperature = 0.2

[llm.prompt]
system_template = "prompts/system/default_read_only.txt"
profile = "strict_read_only"
output_language = "auto" # auto | de | en | de-DE | ...

[llm.policy]
simple = "off"
standard = "optional"
detailed = "preferred"
```

Rules:
- `api_key_env` names an env var, never stores raw secret in TOML.
- `base_url` and `model` are explicit and inspectable.
- missing secret must trigger explicit fallback/error reporting.
- request tuning options are bounded and validated.
- prompt configuration uses file references and fixed profiles, not arbitrary inline role text.

### Prompt and request controls (restricted)

Allowed controls:
- `llm.request.context_budget_tokens`
- `llm.request.max_output_tokens`
- `llm.request.temperature`
- `llm.prompt.system_template`
- `llm.prompt.profile`
- `llm.prompt.output_language`

Purpose:
- `context_budget_tokens`: explicit upper bound for evidence/context sent to model
- `max_output_tokens`: cap output size and cost
- `temperature`: bounded creativity control
- `system_template`: versioned system prompt file path in repo
- `profile`: fixed behavior profile to keep role intent explicit
- `output_language`: desired language for LLM-generated text outputs (`auto` keeps user-question language)

Initial allowed prompt profiles:
- `strict_read_only`
- `review_strict`
- `describe_onboarding`

Explicitly not allowed in this phase:
- free-form inline `system_prompt` text in TOML
- free-form `developer_role` / role-play text fields
- arbitrary runtime prompt assembly from unbounded user config

### Environment variables

Supported overrides (initial):
- `FORGE_LLM_PROVIDER`
- `FORGE_LLM_BASE_URL`
- `FORGE_LLM_MODEL`
- `FORGE_LLM_API_KEY`
- `FORGE_LLM_TIMEOUT_S`
- `FORGE_LLM_OUTPUT_LANGUAGE`

`.env` usage is allowed as local developer mechanism, but Forge behavior is defined in terms of environment variables, not implicit hidden profiles.

### Runtime behavior

For each LLM attempt:
- resolve effective provider config from precedence chain
- validate required fields (`provider`, `base_url`, `model`, secret)
- call OpenAI-compatible chat/completions endpoint
- on failure: deterministic fallback path with explicit reason

Required transparency:
- include provider/model/base_url in LLM usage metadata
- include fallback reason when request is not executed or fails
- preserve provenance section (evidence vs inference)

### Validation and errors

Config validation failures must be explicit and actionable, for example:
- unknown provider value
- missing base URL
- missing model
- `api_key_env` configured but env var absent
- invalid timeout value
- invalid token/temperature range
- unknown prompt profile
- missing or unreadable `system_template` file

No silent downgrade to hidden defaults.

## Design

### Why this shape

Feature 012 introduced controlled LLM integration and policy.
Feature 013 makes provider execution practical while preserving:
- explicitness
- composability
- auditable behavior

### LiteLLM and vLLM position

LiteLLM:
- supported as a preferred gateway option via OpenAI-compatible endpoint
- not exposed as a separate Forge provider type

vLLM:
- supported only when exposed through OpenAI-compatible API
- no vLLM-specific Forge adapter in this phase

This keeps Forge provider surface minimal and avoids premature provider fragmentation.

### Config file strategy

Current recommendation:
- use one central file: `.forge/config.toml`

Reason:
- easier precedence resolution
- fewer discovery rules
- less config sprawl in early phases

Possible later split (not in this feature):
- `.forge/llm.toml` if config volume grows significantly
- only with explicit merge/load-order rules

### Non-goals

- no multi-provider orchestration engine in Forge
- no hidden global/user prompt injection
- no secret persistence in `.forge/config.toml`
- no provider-specific business logic inside capabilities
- no unbounded prompt customization layer
- no generic role-play configuration API

## Definition of Done

- `.forge/config.toml` is supported and documented
- config precedence (CLI > env > TOML > defaults) is implemented and tested
- `openai_compatible` provider executes real requests through configured endpoint
- LiteLLM-compatible operation is validated via integration path
- missing/invalid config paths fail explicitly or fallback explicitly (per policy)
- outputs include LLM usage metadata with provider/model/base URL and fallback status
- quality gates cover:
  - deterministic no-LLM path
  - LLM success path
  - LLM failure/misconfiguration fallback path

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 013; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
