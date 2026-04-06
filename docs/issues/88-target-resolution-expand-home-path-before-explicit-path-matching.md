# Target Resolution Expand ~ Home Paths Before Explicit-Path Matching Against Known Paths

## Problem

Target resolution treats `~`-prefixed inputs as explicit paths but does not expand the home marker before matching against known paths/directories.

This can cause valid user inputs like `~/project/file.py` to be reported as unresolved even when the corresponding absolute path is known.

## Why this matters

- Common shell-style path input fails unexpectedly.
- Resolution behavior becomes inconsistent across equivalent path forms (`~` vs absolute path).
- Users receive false unresolved diagnostics for otherwise valid explicit targets.
- Handoff reliability into downstream foundations degrades.

## Evidence

- Explicit-path detection includes `~`-prefixed values.
- Matching logic compares raw target strings against known path sets.
- Without expansion, `~` form does not equal the absolute form stored in known paths.

## Required behavior

- `~` and `~/...` targets must be expanded to normalized absolute paths before explicit-path matching.
- Equivalent path forms must resolve identically.
- Existing explicit-path behavior for non-home inputs must remain unchanged.

## Done criteria

- Home-prefixed path input resolves correctly when the expanded path exists in known paths/directories.
- Existing non-home explicit-path cases continue to pass.
- Regression tests cover:
  - successful resolution via `~` expansion
  - unresolved result for truly missing expanded targets.

## Scope

This issue is limited to explicit-path normalization in target resolution.

It does not include broad path canonicalization redesign, symlink-policy changes, or cross-platform path strategy rewrites.

## Linked Features

- _To be defined during implementation._

## Suggested implementation direction

- Normalize explicit path targets with home expansion (`Path(...).expanduser()`) before known-path checks.
- Keep matching deterministic and compatible with existing resolution strategy and diagnostics.

## Implemented Behavior (Current)

- Explicit target-resolution path matching now expands home-prefixed inputs (`~`) before comparing against `known_paths` and `known_directories`.
- Resolved explicit-path outputs now consistently use the expanded canonical path when a home-prefixed input matches known targets.
- Existing non-home explicit-path behavior remains unchanged.

## How To Validate Quickly

1. Provide a known path in absolute form.
2. Resolve the same target via `~` form.
3. Confirm both forms return the same resolved target semantics.
4. Confirm unresolved diagnostics still trigger for non-existent expanded paths.

## Known Limits / Notes

- This issue addresses only home-marker expansion in explicit path flows.
- It does not define new behavior for environment-variable path interpolation.
