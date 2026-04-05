# Repository / Workspace Foundation Core Bootstrap

## Description

Implement Foundation 12 as a new parallel core workspace foundation with canonical locators, explicit read/write scope decisions, deterministic workspace snapshots, and file-role classification.

## Spec

- Add a central `WorkspaceContext` contract with deterministic `workspace_snapshot_id`.
- Normalize all path-like references through canonical locators.
- Resolve include/ignore rules with explicit priority layers (`default`, `repo`, `local`, `cli`) and conflict diagnostics.
- Separate read and write policy decisions (`write` deny-by-default).
- Classify files into `source|config|test|docs|generated|artifact|external`.
- Keep runtime behavior of existing modes unchanged.

## Definition of Done

- Foundation 12 API exists in `core/` as parallel implementation.
- Deterministic snapshot, locator normalization, scope decisions, and role classification are covered by tests.
- Diagnostics expose rule provenance (`rule_id`, `rule_source`, `rule_priority`) for ignore/conflict/policy blocks.

## Implemented Behavior (Current)

- New foundation modules exist under `core/workspace_*` and are not wired into existing mode runtime paths.
- `resolve_workspace_context` builds a typed workspace contract and computes deterministic `workspace_snapshot_id`.
- `normalize_locator`, `is_in_read_scope`, `is_in_write_scope`, and `classify_file_role` are available as explicit, typed APIs.
- Include/ignore conflict resolution emits structured diagnostics, and write scope is deny-by-default unless explicit write scopes are configured.

## How To Validate Quickly

1. Run `python3 -m unittest tests/test_workspace_foundation.py`.
2. Confirm all tests pass for snapshot determinism, locator normalization, scope policy, precedence/conflict diagnostics, and role classification.
3. Verify no existing mode runtime wiring changed in this implementation step.

## Known Limits / Notes

- Multi-repo cross-root linking and advanced platform/symlink policy variants are intentionally deferred to later phases.
- Current implementation is foundation-local and prepared for future integrations (retrieval, target resolution, trust/safety, mutation execution).
