# Change Tracking and Changelog Policy

## Problem

Changes were not consistently linked to a feature or issue and not always visible in one canonical changelog.

## Required behavior

- Every implementation change must reference at least one feature or issue.
- Every implementation change must be documented in `CHANGELOG.md`.
- Changelog entries must contain the referenced feature/issue id.

## Done criteria

- `AGENTS.md` contains mandatory contributor rule.
- `CHANGELOG.md` exists and is used.
- Team can trace a change from changelog entry to feature/issue spec.

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references issue 1; status is indexed in `docs/status/issues-index.md`.
- Mandatory contributor policy is enforced via `AGENTS.md` and repository changelog discipline.

## How To Validate Quickly

- Confirm implementation changes reference a Feature ID or Issue ID.
- Confirm product/application changes include matching `CHANGELOG.md` entries.
- Use `python3 scripts/status_index.py build` to refresh status indexes after updates.

## Known Limits / Notes

- This issue defines process policy; enforcement relies on contributor discipline and review.
- If stronger automated enforcement is added, document it in this addendum.
