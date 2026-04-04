# Explain Analysis Limits Are Hardcoded, Not Runtime Configurable

## Problem

Explain facet extraction uses fixed hardcoded caps and thresholds (for example max items/edges), with no runtime settings exposure.

## Evidence

- Multiple hardcoded limits in `modes/explain.py` (for example `[:20]`, `[:24]`, edge/evidence caps).
- No canonical runtime keys for explain facet limits, confidence thresholds, or fallback depth.

## Required behavior

- Explain limits should be configurable through runtime settings with source tracing.
- Defaults remain deterministic and documented.

## Done criteria

- Canonical explain settings exist for major extraction caps.
- Explain output can expose effective limits and setting sources.
- Quality gates validate overridden vs default behavior.

## Linked Features

- [Feature 085 - Explain Runtime Settings Surface for Facet Limits](/Users/tino/PhpstormProjects/forge/docs/features/085-explain-runtime-settings-surface-for-facet-limits.md)

## Implemented Behavior (Current)

- Explain extraction caps are now runtime-configurable through canonical settings keys.
- Explain output publishes effective limit values and source tracing in `sections.explain_limits`.
- Regression coverage validates both overridden limits (repo runtime settings) and defaults.

## How To Validate Quickly

- Run:
  - `python3 scripts/run_quality_gates.py`
- Verify:
  - `gate_explain_runtime_limit_settings` passes.

## Known Limits / Notes

- The current setting set focuses on principal facet caps; further fine-grained thresholds can be added later if needed.
