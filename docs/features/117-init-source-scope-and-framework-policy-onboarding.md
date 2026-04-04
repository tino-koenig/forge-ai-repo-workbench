# Init Source-Scope and Framework Policy Onboarding

## Description

Extend init to capture high-impact source-policy decisions (source scope and framework allowlist) in both interactive and non-interactive modes.

## Addresses Issues

- [Issue 54 - Init Does Not Onboard Source-Scope and Framework Policy Settings](/Users/tino/PhpstormProjects/forge/docs/issues/54-init-does-not-onboard-source-scope-and-framework-policy-settings.md)

## Spec

- Add minimal onboarding controls for source policy:
  - source scope default (`repo_only` or `all`)
  - optional framework allowlist identifiers
- Provide equivalent non-interactive flags.
- Persist selected policy in generated config files using explicit, auditable settings.

## Definition of Done

- Interactive and non-interactive init support policy selection.
- Generated config contains deterministic source-policy settings.
- Regression tests cover policy selection paths.

## Implemented Behavior (Current)

- `forge init` supports source-policy onboarding via:
  - `--source-scope` (`repo_only` or `all`)
  - `--framework-allowlist` (comma-separated framework IDs/versions)
- Interactive mode prompts for default source scope and optional framework allowlist.
- Generated files include deterministic source-policy settings in:
  - `.forge/config.toml` under `[query.source_policy]`
  - `.forge/template-meta.toml` (`source_scope_default`, `framework_allowlist`)

## How To Validate Quickly

- Run:
  - `forge init --template balanced --non-interactive --force --source-scope all --framework-allowlist typo3@12,symfony@7`
- Verify generated:
  - `.forge/config.toml` has `query.source_policy.source_scope_default = "all"` and matching allowlist.
  - `.forge/template-meta.toml` has matching source-policy metadata.

## Known Limits / Notes

- Source policy is currently persisted as explicit onboarding baseline; runtime consumption remains mode-specific.
