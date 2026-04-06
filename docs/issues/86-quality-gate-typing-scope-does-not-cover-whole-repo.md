# Quality Gate Typing Scope Does Not Cover Whole Repo

## Problem

Current quality-gate typing results can be interpreted more broadly than the actual enforced scope justifies.

The active typing gate covers only a selected Foundation-oriented subset rather than the full repository. As a result, a green PASS can be read as a broader statement about repository type health even though substantial parts of the codebase remain outside the enforced gate.

## Why this matters

- PASS status can overstate actual repository-wide typing confidence.
- Teams may assume non-gated areas are protected when they are not.
- Scope ambiguity makes triage, prioritization, and quality communication less reliable.
- Future gate expansion becomes harder when current exclusions are not explicit and auditable.

## Evidence

- The typing gate commands currently target only selected repository paths.
- The enforced gate is narrower than the overall runtime-relevant repository surface.
- Broader mypy runs reveal additional failures outside the gated subset.
- Current PASS signaling does not inherently communicate the difference between scoped Foundation success and whole-repo type health.

## Required behavior

- Quality-gate typing scope must be explicit, centralized, and auditable.
- Gate output must clearly distinguish covered paths from uncovered paths.
- PASS semantics must reflect scoped success only, not imply whole-repo type health.
- Any deliberate exclusions must be visible in configuration and documentation.

## Done criteria

- Typing gate scope is defined from one canonical source.
- Gate output includes scope metadata such as included roots and deliberate exclusions.
- Documentation explains the difference between scoped typing PASS and broader repository typing status.
- Automation verifies that configured scope, reported scope, and documented scope remain aligned.

## Scope

This issue is limited to quality-gate typing scope definition, reporting, and PASS semantics.

It does not require immediate full-repo typing enforcement, and it does not directly fix the broader non-gated mypy failures themselves.

## Implemented Behavior (Current)

- Typing gate scope metadata is now centralized in one canonical source in the quality-gate runner.
- Both typing gates emit explicit scope diagnostics on each run:
  - gate identity and mode
  - included paths/files
  - deliberate exclusions
  - PASS semantics
- Foundation typing gate now reports scoped enforcement semantics (`scoped_success_only`).
- Repo-wide typing gate reports advisory baseline semantics (`baseline_non_regression_only`) with explicit include/exclude scope.
- Unit tests verify that configured scope constants and emitted scope metadata remain aligned.

## Suggested implementation direction

- Move typing-scope definition to a single canonical configuration source.
- Emit scope diagnostics during each typing-gate run.
- Adjust PASS wording or reporting structure so scoped success cannot be misread as whole-repo success.
- Support a separate broader typing mode or companion report for non-gated coverage.

## How To Validate Quickly

1. Run the typing gate and inspect the reported scope.
2. Compare included roots and exclusions against repository module roots.
3. Confirm the output clearly signals scoped success rather than whole-repo type health.
4. Confirm documented scope matches configured and emitted scope.

## Known Limits / Notes

- This issue targets scope correctness and signaling, not direct elimination of all existing type errors.
- Full enforcement can remain phased, but the current gate boundary must be explicit.
- Broader repo-wide typing debt can remain tracked separately as its own issue.
