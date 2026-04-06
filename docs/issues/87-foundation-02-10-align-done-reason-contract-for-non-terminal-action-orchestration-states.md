# Foundation Done Reason Contract Mismatch Between Orchestration and Output Contract

## Problem

Foundation 02 orchestration and Foundation 10 output-contract currently disagree on the allowed shape of `done_reason` for `action_orchestration` in non-terminal flows.

In orchestration, ongoing decisions such as `decision="continue"` are modeled with `done_reason=None`. In the output-contract validation path, `done_reason` is enforced as a required field for `action_orchestration` in `available` and `fallback` states and is additionally required to be a `str`. As a result, a semantically valid non-terminal orchestration state from Foundation 02 can be rejected by Foundation 10 as invalid.

## Why this matters

- Two Foundations currently define incompatible contracts for the same orchestration payload family.
- A valid non-terminal orchestration state can fail validation solely because of cross-foundation contract drift.
- Downstream diagnostics become misleading because they report an invalid payload where the real problem is contract inconsistency.
- This weakens confidence that Foundation 10 is validating the semantics actually produced by Foundation 02.

## Evidence

- Foundation 02 explicitly models ongoing orchestration decisions such as `decision="continue"` with `done_reason=None`.
- Foundation 10 currently requires `done_reason` to be present for `action_orchestration` in `available` and `fallback` states.
- Foundation 10 also validates `done_reason` as `str`, which excludes the `None` value emitted by valid non-terminal orchestration flows.
- The result is a direct contract incompatibility between orchestration production and output-contract validation.

## Required behavior

- Foundation 02 and Foundation 10 must share one canonical contract for `done_reason` in `action_orchestration`.
- Non-terminal orchestration states must validate successfully when they follow the canonical contract.
- The contract must clearly distinguish terminal versus non-terminal meaning for `done_reason`.
- Validation diagnostics must fail only for true contract violations, not for valid cross-foundation payloads.

## Done criteria

- The canonical contract explicitly defines whether `done_reason` is:
  - nullable for non-terminal states
  - required only for terminal states
  - or otherwise state-dependent by explicit rule
- Foundation 02 emitted payloads and Foundation 10 validation rules are aligned to that single definition.
- Regression coverage includes at least:
  - valid non-terminal `decision="continue"` payload with the canonical `done_reason` shape
  - valid terminal orchestration payload with the required terminal `done_reason` shape
  - invalid payloads that violate the newly explicit rule
- Diagnostics precisely reflect the final contract semantics.

## Scope

This issue is limited to `done_reason` contract alignment between Foundation 02 orchestration and Foundation 10 output-contract validation for `action_orchestration`.

It does not cover unrelated orchestration fields, broader minimum-field enforcement, or other builder/validator mismatch issues already tracked separately.

## Suggested implementation direction

- Define the canonical `done_reason` rule in one shared place or one explicitly referenced contract source.
- Decide explicitly whether `done_reason` is optional, nullable, or state-dependent.
- Update both orchestration emission and output-contract validation to follow the same rule.
- Preserve strict validation, but only against the final shared semantics.

## Implemented Behavior (Current)

- Foundation 10 output-contract validation now accepts `action_orchestration.payload.done_reason = null` when present.
- This aligns with Foundation 02 non-terminal orchestration semantics where ongoing `continue` decisions can carry `done_reason=None`.
- Minimum-field enforcement for `action_orchestration` remains unchanged; the fix only removes the cross-foundation type mismatch for non-terminal payloads.

## How To Validate Quickly

1. Produce a non-terminal `action_orchestration` payload from Foundation 02 with `decision="continue"`.
2. Validate that payload through Foundation 10.
3. Confirm that semantically valid non-terminal payloads pass under the canonical rule.
4. Confirm that terminal payloads still require the correct terminal `done_reason` behavior.
5. Confirm that truly invalid `done_reason` shapes still fail with precise diagnostics.

## Known Limits / Notes

- This issue is about cross-foundation contract compatibility for `done_reason`.
- It should not broaden unrelated orchestration semantics.
- Minimum required fields for `action_orchestration` remain a separate issue and should not be conflated with this nullable/state-dependent contract question.
