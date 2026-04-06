

# Workspace Symlink Policy Can Be Bypassed for Nonexistent Target Paths

## Problem

When `allow_symlinks=False`, the current implementation may return `False` early in `_contains_symlink(...)` if the target path does not yet exist.

As a result, symlink traversal can be implicitly allowed for paths that are created later or resolved at runtime, bypassing the intended policy.

## Why this matters

Foundation 12 defines the **trusted workspace boundary** and governs read/write safety.

If symlink handling can be bypassed:

- scope checks can be inconsistent,
- write paths may operate outside intended boundaries,
- security assumptions (deny-by-default for write) can be weakened,
- behavior differs depending on path existence timing.

This is a correctness and safety issue in the workspace contract.

## Evidence

- `_contains_symlink(...)` returns early when the candidate path does not exist.
- `is_in_read_scope` / `is_in_write_scope` rely on this helper when `allow_symlinks=False`.
- For nonexistent targets, symlink traversal is not detected and therefore not blocked.

## Required behavior

- Symlink policy must be enforced **independently of path existence**.
- Traversal through any symlink component between `workspace_root` and the target must be detected and handled according to policy.
- Behavior must be deterministic and consistent for existing and non-existing paths.

## Done criteria

- `_contains_symlink(...)` (or equivalent) evaluates the path segments from `workspace_root` to the target without relying on the final path existence.
- Symlink traversal is correctly detected even if the final path does not exist.
- `is_in_read_scope` and `is_in_write_scope` enforce `allow_symlinks=False` consistently.
- Regression tests cover:
  - existing path with symlink in chain → blocked
  - nonexistent path with symlink in chain → blocked
  - paths without symlinks → allowed when in scope

## Scope

This issue is limited to **symlink detection and policy enforcement** in Foundation 12.
It does not require redesigning the overall workspace model.

## Suggested implementation direction

- Evaluate each path segment starting from `workspace_root` toward the target.
- Check `is_symlink()` on each segment that exists.
- Do not short-circuit based on final path existence.
- Keep behavior deterministic across platforms.

## How To Validate Quickly

1. Create a symlink within the workspace (e.g. `src/link -> /external/path`).
2. Check a nonexistent path under that symlink.
3. Call `is_in_read_scope` / `is_in_write_scope` with `allow_symlinks=False`.
4. Confirm that the access is blocked.

## Known Limits / Notes

- Platform-specific filesystem behavior (especially on Windows) must be considered.
- This fix should not introduce implicit path resolution differences between Foundations.