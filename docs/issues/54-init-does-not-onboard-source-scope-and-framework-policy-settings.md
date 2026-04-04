# Init Does Not Onboard Source-Scope and Framework Policy Settings

## Problem

Init templates/onboarding currently do not expose source-scope/framework policy decisions for retrieval behavior.
This leaves teams without an explicit first-run policy surface for repo-only vs framework-inclusive flows.

## Evidence

- Generated init config includes query planner/orchestrator and index enrichment defaults.
- No source-scope/framework allowlist settings are generated or asked in interactive init flow.
- Feature 044 spec explicitly calls out optional source-policy defaults and framework IDs when framework-aware retrieval is enabled.

## Required behavior

- Init should provide a minimal, explicit policy surface for source scope and framework policy when relevant.
- Non-interactive mode should support deterministic flags for the same settings.

## Done criteria

- Interactive init can set source scope baseline (`repo_only` vs `all`) and optional framework allowlist.
- Non-interactive init supports equivalent flags.
- Generated config reflects selected policy deterministically.

## Linked Features

- [Feature 117 - Init Source-Scope and Framework Policy Onboarding](/Users/tino/PhpstormProjects/forge/docs/features/117-init-source-scope-and-framework-policy-onboarding.md)

## Implemented Behavior (Current)

- The issue is resolved in the current implementation and tracked by its linked feature document.
- Regression coverage for the failing behavior is included in `scripts/run_quality_gates.py`.

## How To Validate Quickly

1. Reproduce with the previously failing scenario from this issue document.
2. Run `python3 scripts/run_quality_gates.py` and confirm the linked gate passes.
3. Verify command output/JSON contract no longer shows the reported failure mode.

## Known Limits / Notes

- The fix is scoped to the contract described in this issue; adjacent behavior remains governed by existing feature boundaries.
