# Ask Ignores `access.web` Runtime Setting

## Problem

`ask:docs` and `ask:latest` execute web search/retrieval even when runtime setting `access.web` is `false`.

Observed behavior:
- Runtime registry defines `access.web` (default `false`).
- Ask mode always enters web pipeline for presets `docs|latest`.
- No policy gate blocks outbound web search/retrieval based on runtime access settings.

This breaks expected runtime access control semantics.

## Required behavior

- Ask web stages must honor effective runtime access policy.
- With `access.web=false`, web search/retrieval must be skipped deterministically and reported as policy-blocked.
- Output metadata should expose that web usage was denied by runtime policy (not network/provider fallback).

## Done criteria

- `ask:docs` / `ask:latest` with `access.web=false` do not execute web foundations.
- Contract sections include explicit policy-blocked reason.
- Regression test covers both blocked and allowed (`access.web=true`) behavior.

## Linked Features

- [072-ask-web-access-policy-and-settings-integration.md](/Users/tino/PhpstormProjects/forge/docs/features/072-ask-web-access-policy-and-settings-integration.md)

## Implemented Behavior (Current)

- Ask web presets now enforce runtime `access.web` before invoking web foundations.
- With `access.web=false`, `ask:docs` and `ask:latest` skip both web search and web retrieval deterministically.
- Ask output now exposes explicit policy metadata under `sections.ask.access_policy` including source and blocked reason.

## How To Validate Quickly

- Blocked path:
  - set `.forge/runtime.toml` to `"access.web" = false`
  - run `python3 forge.py --output-format json --llm-provider mock ask:docs "latest typo3 news"`
  - verify `sections.ask.access_policy.web_policy_blocked == true`
  - verify `sections.ask.search.used == false` and `sections.ask.retrieval.used == false`
- Allowed path:
  - set `.forge/runtime.toml` to `"access.web" = true`
  - rerun command and verify `sections.ask.access_policy.web_policy_blocked == false`

## Known Limits / Notes

- This issue covers access gating and reporting; budget tuning and freshness semantics are handled in subsequent features/issues.
