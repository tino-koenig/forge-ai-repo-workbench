# Index

## Description

The Index feature builds and maintains a lightweight local repository index under `.forge/`.

The index is a structural helper and performance aid for Forge. It is not the product itself, and it must not become a mandatory heavy subsystem.

The index should help Forge:
- discover files and directories faster
- classify repository structure
- improve candidate selection for later capabilities
- support explanation, review, description, and test drafting

The index may write only inside `.forge/`.

## Spec

### Commands

- `forge index`
- later optionally:
    - `forge index refresh`
    - `forge index inspect`

### Allowed effects

- may read the repository
- may write under `.forge/`
- must not modify repository files outside `.forge/`

### Core output

Initial output file:
- `.forge/index.json`

Later formats may evolve, but the initial version should remain easy to inspect and debug.

### What is indexed

The index should include both:

- files
- directories

#### File entries

Each file entry should contain, where available:

- path
- kind = `file`
- extension / language guess
- size
- mtime
- optional hash
- optional top-level symbols if cheaply available
- path classification
- index participation state

#### Directory entries

Each directory entry should contain, where available:

- path
- kind = `directory`
- depth
- child counts
- dominant file extensions if cheaply derivable
- path classification
- index participation state

### Path classification

The index must distinguish between different path classes.

Initial path classes:

- `hard_ignore`
- `index_exclude`
- `low_priority`
- `normal`
- `preferred`

#### Meaning

##### `hard_ignore`
The path is ignored completely:
- not indexed
- not searched by default
- not considered by capabilities unless explicitly forced later

Examples:
- `.git/`
- temporary output
- coverage artifacts
- editor metadata
- cache-only directories

##### `index_exclude`
The path is not included in the structural index, but it is not treated as irrelevant forever.

It may still be used later by explicit or capability-specific operations.

Example:
- `vendor/`

This distinction is important because some directories are too large or noisy for indexing, while still being relevant for understanding dependencies, inheritance, or external interactions.

##### `low_priority`
The path is indexed, but should generally receive lower weight unless a capability specifically values it more.

Examples:
- `docs/`
- `scripts/`
- `examples/`

##### `normal`
The path is indexed with default priority.

##### `preferred`
The path is indexed and should generally be considered structurally important.

Examples:
- `src/`
- `Configuration/`
- `tests/`
- framework-specific core paths

### Important rule

The index stores structure and classification.  
It does not make final relevance decisions for all capabilities.

Capabilities such as `query`, `describe`, `review`, or `test` may interpret indexed paths differently based on their own logic.

For example:
- `docs/` may be low priority for code-location queries
- `docs/` may be highly relevant for `describe`

### Config sources

All functional configuration must live inside the repository.

There are no out-of-repo defaults that influence repo behavior.

#### Repo config files

- `.forge/config.toml` (versioned, repo-owned baseline)
- `.forge/config.local.toml` (optional local override, not versioned)

#### Runtime environment outside the repo

Outside the repo, Forge may use:
- tokens
- model credentials
- runtime paths
- cache locations
- machine-specific execution settings

But it must not load repo behavior defaults from user directories.

### Config responsibilities

#### `.forge/config.toml`
Defines the shared repository defaults used by runtime behavior.

Current index-relevant contents:
- `[index.enrichment]`
  - `enabled`
  - `summary_version`
  - `max_summary_chars`

#### `.forge/config.local.toml`
Defines optional machine-local overrides for repository config values.

Typical use:
- local experimentation with index enrichment settings
- temporary local tuning without changing versioned repo defaults

### Merge order

The configuration merge order should be:

1. minimal built-in Forge defaults
2. `.forge/config.toml`
3. `.forge/config.local.toml`
4. CLI overrides

Environment variables or machine-local config must not override functional repo behavior.

### Built-in defaults

Built-in defaults should remain minimal.

They exist only to make Forge usable before repo config is added.

They should cover only obvious universal cases such as:
- `.git/`
- `.forge/`
- clearly disposable build/cache metadata where reasonable

The real repo behavior should come from repository-owned `.forge/config.toml` with optional local override via `.forge/config.local.toml`.

### Index participation vs future usage

The system must clearly separate:

- whether something is indexed
- whether something may be searched later
- how strongly something is weighted by a capability

This is why `vendor/` should usually be `index_exclude`, not `hard_ignore`.

### Future extension points

Not required in the first implementation, but the index should be designed so it can later support:

- incremental refresh
- symbol extraction
- directory role summaries
- framework-aware structural hints
- relationship hints between files and directories

## Design

### Why include directories?

Directories are meaningful structural units in real repositories.

Later Forge capabilities should be able to reason about folder roles such as:
- `docs/`
- `Configuration/`
- `src/`
- `tests/`

This does not mean the index itself must fully explain them yet.  
It means the index should preserve enough structure for later capabilities to do so.

### Why distinguish path classes?

A simple ignore list is not enough.

Forge needs to treat paths differently depending on whether they are:
- useless noise
- too large for indexing
- still relevant for later understanding
- structurally important

Without this distinction, the system becomes either too noisy or too blind.

### Why keep config in the repo?

Forge should behave consistently for every user and every environment working on the same repository.

Repo behavior must not depend on hidden per-user defaults outside the repo.

This improves:
- reproducibility
- team consistency
- CI reliability
- debugging
- trust

### Why keep built-in defaults minimal?

Forge should not impose too much hidden opinion from the core.

If repo structure matters, the repository should describe it explicitly.

### Why JSON first?

The initial index file should be:
- inspectable
- easy to debug
- easy to generate
- easy to consume from later capabilities

JSON is sufficient for the first phase.

## Definition of Done

- `forge index` creates `.forge/index.json`
- the index includes both files and directories
- path classes are represented clearly
- `.forge/config.toml` and `.forge/config.local.toml` are supported as repo-local config inputs
- merge order is deterministic and documented
- `hard_ignore` and `index_exclude` are treated differently
- `vendor/`-style paths can be excluded from indexing without becoming invisible to Forge forever
- no repository files outside `.forge/` are modified
- at least one other capability can consume the index meaningfully

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 002; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.
- `forge index` now reports index-entry delta counts in command output:
  - `new_entries`
  - `updated_entries`
- `.forge/index.json` now persists structured delta metadata under `delta` (including `new_entries` and `updated_entries`).

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
