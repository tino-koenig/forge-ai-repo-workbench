# Changelog

All notable changes to Forge should be documented in this file.

## Unreleased

### Added
- issue 1: status index for features/issues with defined and implemented dates via `scripts/status_index.py` and `docs/status/*`
- issue 1: issue folder bootstrap in `docs/issues/`
- feature 046: query ranking now includes bounded path-segment/full-path and indexed `top_level_symbols` signals with short-token guardrails (e.g. `api`)
- feature 046: query output now exposes retrieval-source metadata (`retrieval_source`) and source-origin metadata (`source_type`) with repo-first source-aware ranking
- feature 047: explain now supports directional and source-scoped facet analysis for `symbols`/`dependencies`/`resources`/`uses` with edge sections (`dependency_edges_out`, `dependency_edges_in`, `resource_edges`)
- feature 048: added deterministic `.forge/graph.json` edge cache (incremental file-hash reuse) and read-only graph consumption in explain/query, including optional framework graph references
- feature 062: added runtime settings foundation (canonical registry + deterministic resolver with source tracing) and wired runtime overrides into CLI bootstrap, profile defaults, doctor diagnostics, and llm mode/model config precedence
- feature 063: added named session context with repo-local persistence, auto-create + TTL enforcement, `forge session` lifecycle commands, revive flow, and runtime-source integration (`session:<name>`)
- feature 061: added top-level `forge set/get` runtime settings UX with canonical keys + aliases, scope persistence (`session|repo|user`), and resolved source inspection (`forge get --source`)
- feature 035: explicit LLM output-language control (`--llm-output-language`, `FORGE_LLM_OUTPUT_LANGUAGE`, `llm.prompt.output_language`)
- feature 025: `--from-run` support for `explain`/`review`/`test`/`describe` with deterministic payload resolution and provenance metadata
- feature 024: `forge runs prune` with `--dry-run`, retention criteria (`--keep-last`, `--older-than-days`), config defaults, and safe JSONL rewrite
- feature 021: structured explain synthesis with `evidence_facts`, `inference_points`, `confidence`, and detailed `role_hypothesis_alternatives`
- feature 036: central mode capability contract with query read-only boundary enforcement and visible policy-violation events
- feature 037: bounded LLM query action orchestration with allowed action catalog, decision contract, budget limits, and explicit done reasons
- feature 038: adaptive query retrieval with explain-derived reranking signals, low-confidence continuation, and explicit rationale output
- feature 039: index explain-summary enrichment metadata with incremental recomputation and query-side read-only consumption
- feature 040: explicit mode-transition policy graph with transition gates, confirmation control, and traceable from-run transition metadata
- feature 045: run history now always stores structured `output.contract` across text and json capability runs
- feature 041: added packaging-based development invocation model (`forge` console script + `python -m forge` compatibility)
- feature 042: documented workstation/user installation via `pipx` with global `forge` invocation plus explicit upgrade/uninstall lifecycle
- feature 043: repository context now resolves via nearest ancestor `.forge/` marker (auto-discovery from cwd or `--repo-root`) with explicit `forge init` guidance when missing
- feature 044: added `forge init` with interactive and non-interactive template setup, dry-run/overwrite safeguards, and generated repository-owned `.forge` baseline files
- feature 049: query action orchestration now executes as a bounded iterative state machine with explicit per-iteration trace and deterministic done reasons
- feature 050: query orchestration now uses explicit action handlers for all catalog actions with per-iteration handler diagnostics and bounded search expansion
- feature 051: query orchestration now applies deterministic progress scoring with source-aware weighting and no-progress stop criteria (`done_reason=no_progress`)
- feature 052: query now exposes stable per-iteration orchestration trace diagnostics (budgets, source scope/distribution, snapshots, fallback/block reasons) in JSON and full text view
- feature 053: added optional `.forge/frameworks.toml` source profiles with `--framework-profile` query selection, read-only local framework path retrieval, and source provenance metadata (`source_type`/`source_origin`/framework identity)
- feature 054: added dedicated free-question `ask` mode (`ask`, `ask:repo`, `ask:docs`, `ask:latest`) with compact default output, explicit ask metadata in contract, and staged warnings for `ask:latest`/`--guided`
- feature 055: added reusable web-search foundation with host allowlist policy, bounded candidate discovery/ranking, and `ask:docs`/`ask:latest` integration via `sections.ask.search`
- feature 056: added reusable web-retrieval foundation with bounded host-allowlisted fetch/snippet extraction and `ask:docs`/`ask:latest` integration via `sections.ask.retrieval`
- feature 057: added reusable LLM foundation (`core/llm_foundation.py`) with shared policy/settings/prompt/provider/run-step APIs and integrated delegation from `core/llm_integration.py`

### Changed
- feature 116 / issue 53: init-template- und option-domains wurden in eine zentrale foundation (`core/init_foundation.py`) ueberfuehrt; CLI-choices und init-mode nutzen nun dieselbe registry inkl. drift-gate
- feature 111: logs-filtering und protocol-analytics wurden in eine zentrale foundation (`core/protocol_analytics_foundation.py`) extrahiert; `modes/logs.py` ist nun ein duenner adapter bei stabilem output-contract
- feature 109 / issue 47: `forge logs --capability`-choices werden nun aus `core.capability_model.Capability` abgeleitet; ein quality-gate prueft parser/model-drift deterministisch
- feature 107 / issue 8: protocol-log-redaction behaelt nicht-sensitive `token_usage`-zaehler (`prompt_tokens`, `completion_tokens`, `total_tokens`, `source`) bei und maskiert weiterhin secrets/auth-token deterministisch
- feature 106 / issue 7: policy-deaktivierte, nicht versuchte LLM-stages (z. B. summary refinement bei query JSON) erzeugen keine `step_type=llm`-fallback-events mehr; logs-fallback-analytics zaehlt damit nur reale Versuche
- feature 114 / issue 51: `forge init` setzt im repo-baseline-config keinen konkreten LLM-provider mehr; dadurch bleibt `config_validation` nach init konsistent, waehrend provider-setup als expliziter onboarding-warn in `doctor` erscheint
- feature 105 / issue 11: index-konfigurationsvertrag auf TOML-basiertes Ist-Verhalten harmonisiert (`.forge/config.toml` + `.forge/config.local.toml`) und per Doku-Gate gegen Rueckfall auf nicht implementierte YAML-dateien abgesichert
- feature 110 / issue 48: `config_validation` prueft `logs.protocol` jetzt explizit (ranges + timestamp-format) und meldet Fehlkonfigurationen sichtbar in `doctor`/`config validate` statt stiller Korrektur
- feature 108 / issue 46: protocol-log settings werden jetzt zentral aus `core.config` aufgeloest (inkl. `.forge/config.local.toml`-Precedence) statt lokalem Direkt-Parsing in `core/protocol_log.py`
- feature 118 / issue 55: init nutzt planner/orchestrator-defaults jetzt aus zentralen `core.config`-Konstanten; doppelte Literalwerte wurden entfernt und per Gate gegen Drift abgesichert
- feature 104 / issue 45: `config_validation` schlaegt nun deterministisch fehl, wenn bei `provider=openai_compatible` Pflichtfelder (`base_url`, `model`) fehlen; `doctor` und `config validate` melden dies konsistent
- feature 103 / issue 44: `config_validation` erkennt nun unbekannte Keys schema-basiert in `.forge/config.toml` und `.forge/config.local.toml` (inkl. Pfaddetail und Did-you-mean-Hinweis) und meldet diese konsistent in `doctor`/`config validate` als fail
- feature 099 / issue 4: runtime diagnostics melden `scope_paths.session` jetzt konsistent zur effektiven session-herkunft (env, named oder merged)
- feature 098 / issue 3: `forge set --scope repo|user` bewahrt unbekannte runtime-keys/tabellen nun beim schreiben statt destruktivem rewrite
- feature 101 / issue 42: auto-erstellte sessions nutzen nun konfigurierbare runtime-ttl (`session.default_ttl_minutes`) mit source-tracing in runtime-diagnostics
- feature 100 / issue 41: session-touch operationen (`session use`, `set --scope session`, `session clear-context`) aktualisieren nun konsistent `last_activity_at` und `expires_at`
- feature 102 / issue 43: `doctor` und `config validate` erzeugen keine session-artefakte mehr; read-only-vertrag fuer `.forge/sessions` ist per gate abgesichert
- feature 113 / issue 50: init invalid-target failures erzeugen keine verzeichnisse oder `.forge`-artefakte mehr; no-write-vertrag ist per gate abgesichert
- feature 112 / issue 49: init non-mutating and precondition-failure paths (`--list-templates`, `--dry-run`, non-tty interactive) no longer persist run history or create `.forge` marker side effects
- feature 034: added deterministic protocol-log redaction/privacy guards (secret/token masking, bearer/auth scrubbing, prompt hash+length persistence, and synthetic leak regression gate)
- feature 033: added `forge logs` filtering (`run-id/capability/step-type/status/time/provider/model`) and persisted-event analytics via `forge logs stats` (counts, p50/p95, slowest steps, fallback rate, provider/model snapshot)
- feature 032: added read-only protocol log viewer commands (`forge logs tail|run|show`) with run-focused timelines, totals, problematic-step highlighting, and JSON/text output
- feature 031: added protocol JSONL storage (`.forge/logs/events.jsonl`) with configurable size/age/count retention, timestamped rotation archives, and quality-gate coverage
- feature 030: introduced a canonical step protocol/event model and persisted protocol-compliant `execution.protocol_events` in run history, including explicit deterministic/io steps and optional llm steps with bounded metadata
- feature 029: added explicit LLM token/cost tracking in usage metadata (`token_usage`, `cost_tracking`, `cost`) with pricing config support, unknown fallbacks, and planner/orchestrator usage coverage
- issue 1: contributor guidance now requires changelog entries with feature/issue reference for each change
- feature 002: `forge index` now reports entry delta counts (`new_entries`, `updated_entries`) in CLI output and persists structured delta metadata in `.forge/index.json`
- feature 021: explain now derives deterministic behavior signals from target content (guards, file I/O, serialization, redaction, log-path anchors) and includes them in summary/full view/JSON
- feature 058: added explain facet alias routing (`explain:<facet>`) plus `--focus` option with deterministic conflict validation and explain focus provenance in output contracts
- feature 059: implemented `explain:settings` and `explain:defaults` facets with deterministic direct answers plus structured `settings_influences`/`default_values` evidence sections in text and JSON
- feature 060: implemented `explain:llm` and `explain:outputs` facets with deterministic direct answers plus structured `llm_participation`/`output_surfaces` sections in text and JSON
- feature 041: console entrypoint import now uses `forge_cmd.cli` (renamed from `cmd.cli`) to avoid stdlib `cmd` module collision in installed environments
- issue 2: fixed installed `forge` entrypoint import failure (`cmd` stdlib collision) by renaming internal package from `cmd` to `forge_cmd`
- feature 046: query search term pipeline now prioritizes symbol-like/code-variant terms, suppresses weak generic terms by default (including `where` outside SQL-like context), and applies weighted evidence scoring for content/path/symbol/summary retrieval
- feature 046: removed hardcoded intent-specific query boosts/hints (`entrypoint`, `llm`, `api_call`) from base term derivation and candidate scoring to keep core ranking behavior explicit and neutral
- feature 046: simplified planner-driven term derivation to use planner outputs directly (`search_terms` + `code_variants`) before deterministic filtering/prioritization
- feature 046: planner-driven query term derivation now uses `search_terms` only; `code_variants` are no longer injected into base query retrieval terms
- feature 046: removed term-class branching (`primary/secondary/fallback`) from `derive_search_terms`; term order is now preserved and scoring priority derives from search-term position plus evidence source
- feature 028: query planner now supports prioritized term buckets (`lead_terms`, `support_terms`) and query retrieval consumes them in stable order before fallback `search_terms`
- feature 028: planner normalization now demotes generic terms (for example `code`, `location`, `file`, `module`) from `lead_terms` to `support_terms` to keep lead terms precise
- feature 049: query `read` action now caps per-iteration inspected files to the same three-candidate bounded context window used by `enrich_detailed_context`, aligning `budget_files_used` with actual read scope
- feature 049: query orchestration loop no longer terminates early from a default `sufficient_evidence` state when decision is `continue`; termination now reflects actual stop conditions
- feature 049: query summary refinement now discards contradictory LLM rewrites that negate deterministic location findings (for example "not found" against known candidate files)
- feature 049: query summary refinement now also requires retaining deterministic top-path anchors; rewrites that drop all anchored paths are discarded as contradictory/noisy
- feature 049: query summary refinement now runs only for human text output (`--output-format text`); JSON output keeps deterministic summaries unchanged
- feature 049: query summary refinement enforces deterministic-summary preservation (append-only style); rewrites that do not retain core deterministic claims are discarded
- feature 049: query summary refinement prompt now uses strict JSON with `preserved_summary` (exact deterministic echo) plus optional `style_addendum`; non-conforming responses are rejected deterministically
- feature 049: query `style_addendum` is now accepted only when it references a deterministic top-path anchor; generic non-anchored addenda are dropped
- feature 049: query refinement now always emits deterministic summary only (no claim-bearing addendum accepted), preventing semantic drift in text output
- feature 049: query orchestration adds deterministic anti-stall override from repeated `search` no-op to bounded `read`, reducing no-progress loops on stable candidate sets

## 2026-04-03

### Added
- feature 019: externalized review rules (`.forge/review-rules.toml`) with validation, review integration, and quality gates
- feature 018: expanded regression fixture suite and additional quality gates
- feature 017: redacted LLM observability
- feature 016: prompt profile policy and mapping
- feature 015: describe and test JSON output contracts
- feature 014: doctor/config-validate capability and setup checks
- feature 013: OpenAI-compatible provider and TOML-based LLM config
- feature 012: controlled LLM integration path
- feature 011: capability quality-gate suite
- features 008-010: shared analysis primitives, index consumption, and output contracts

### Changed
- feature 023/026: human-first output views and default output cleanup
- feature 027/028: cross-lingual term expansion and LLM query planner integration

### Added (Earlier in phase)
- features 001-007: core CLI and capability model, index, query, explain, review, describe, and test drafting foundations
