# Index

## Description

The Index feature builds and maintains a lightweight local repository index under `.forge/`.

The index is a helper, not a requirement. Forge must still work without it, but use it when present.

The index supports:
- faster discovery
- better candidate selection
- structural awareness for later capabilities

## Spec

### Command

- `forge index`

### Allowed effects

- may read the repository
- may write under `.forge/`
- must not modify project files

### Initial indexed data

Per file:
- path
- extension / language guess
- size
- mtime
- optional hash
- top-level symbols if cheaply available
- optional section headers for markdown/text files

### Storage

Initial format:
- `.forge/index.json`

### Behavior

- create or refresh index
- skip ignored paths
- remain lightweight and debuggable
- support incremental refresh later

## Design

### Why not make it mandatory?

Forge must remain useful without heavy setup. The index is a performance and structure feature, not a gatekeeper.

### Why JSON first?

- simple
- inspectable
- easy to debug
- enough for early versions

### Role in the system

Other features may use the index opportunistically:
- query
- explain
- review
- describe
- test

## Definition of Done

- `forge index` creates `.forge/index.json`
- ignored paths are excluded
- file metadata is stored reliably
- the index can be consumed by at least one other capability
- no project files outside `.forge/` are modified