# Foundation Action Orchestration Builder/Validator Contract Mismatch

## Problem

Foundation action orchestration currently contains an internal output-contract mismatch between the builder and the validator.

The builder strips or omits normative `decision` and `control_signal` fields from `action_orchestration` payloads, while the validator still evaluates those fields as part of the contract. As a result, a payload shape produced by the system itself can be treated as incomplete or invalid by the corresponding validation path.

## Why this matters

- The system no longer has a single trustworthy contract for `action_orchestration`.
- Internally generated payloads can fail validation for reasons caused by contract drift rather than caller error.
- Runtime diagnostics become misleading because reported violations may reflect builder/validator inconsistency, not malformed external input.
- Contract drift at this layer weakens predictability for downstream orchestration behavior and future refactors.

## Evidence

- The builder path removes or fails to preserve `decision` and `control_signal` in `action_orchestration` payload construction.
- The validator still treats those fields as normative when evaluating the same payload family.
- The current implementation therefore allows a builder-produced payload shape that is not aligned with validator expectations.

## Required behavior

- Builder and validator must operate against one canonical `action_orchestration` contract.
- Normative fields must either be emitted by the builder or no longer be treated as required/normative by the validator.
- A payload produced by normal builder flows must validate successfully without repair, post-processing, or special-case normalization.
- Validation errors must identify real contract violations only.

## Done criteria

- Shared contract rules for `action_orchestration` are defined once and reused by both builder and validator paths.
- Builder-produced payloads validate successfully in normal flows.
- Regression coverage includes:
  - at least one valid builder-generated payload that passes validation
  - at least one genuinely malformed payload that fails with a precise diagnostic
- The fix explicitly covers the `decision` and `control_signal` mismatch.

## Scope

This issue is limited to Foundation contract alignment between `action_orchestration` payload construction and validation.

It does not cover broader contract expansion, new orchestration states, or unrelated typing cleanup elsewhere in the repository.

## Implemented Behavior (Current)

- The `action_orchestration` section builder now preserves the normative fields `decision` and `control_signal`.
- Builder output and validator semantics are now aligned for these fields: payloads produced by normal builder flow are no longer silently stripped before validation.
- Regression coverage now asserts this path explicitly by validating a builder-produced payload containing malformed normative values and confirming precise validator diagnostics.

## Suggested implementation direction

- Extract or centralize the canonical `action_orchestration` field contract.
- Decide explicitly whether `decision` and `control_signal` are canonical output fields or non-normative/internal fields.
- Update builder and validator to follow that single decision consistently.
- Preserve strict validation, but only against the shared canonical contract.

## How To Validate Quickly

1. Produce `action_orchestration` payloads through standard builder flows.
2. Validate those payloads through the Foundation validator.
3. Confirm that valid builder-generated payloads pass unchanged.
4. Confirm that intentionally malformed payloads still fail with precise diagnostics.

## Known Limits / Notes

- This issue fixes internal contract consistency only.
- It should not introduce new orchestration behavior.
- Minimum required core fields for `available` and `fallback` states are tracked separately and should not be conflated with this mismatch fix.
