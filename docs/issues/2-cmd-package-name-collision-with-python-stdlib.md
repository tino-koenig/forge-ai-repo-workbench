# Cmd Package Name Collision with Python Stdlib

## Problem

The installed `forge` console entrypoint failed with:

- `ModuleNotFoundError: No module named 'cmd.cli'; 'cmd' is not a package`

Root cause was a package name collision between Forge's internal package name `cmd` and Python's stdlib module `cmd`.

## Required behavior

- Console entrypoint imports must resolve deterministically in installed environments.
- Internal package names must not collide with stdlib module names in ways that break runtime imports.
- `forge --help` and `forge query ...` must work after editable install.

## Done criteria

- Internal package `cmd` is renamed to a non-colliding module namespace.
- Entrypoint import and packaging discovery are updated accordingly.
- Query entrypoint hint paths are updated to the new package path.
- Changelog and status tracking reference this issue.

## Implemented Behavior (Current)

- Internal package path was renamed from `cmd` to `forge_cmd`.
- Entrypoint import now uses `from forge_cmd.cli import main as cli_main`.
- Package discovery now includes `forge_cmd` instead of `cmd`.
- Runtime no longer resolves against stdlib `cmd` for Forge CLI boot.

## How To Validate Quickly

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
forge --help
forge query "hallo"
```

Expected:
- `forge --help` prints CLI help without import error.
- `forge query "hallo"` executes normally.

## Known Limits / Notes

- If editable install cannot run due to offline dependency resolution, `python3 -m forge --help` still validates module import path locally.
- After package-layout changes, rerun editable install so console scripts point to current modules.
