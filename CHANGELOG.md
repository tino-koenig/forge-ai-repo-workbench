# Changelog

All notable changes to Forge should be documented in this file.

## Unreleased

### Added
- issue 1: status index for features/issues with defined and implemented dates via `scripts/status_index.py` and `docs/status/*`
- issue 1: issue folder bootstrap in `docs/issues/`
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

### Changed
- issue 1: contributor guidance now requires changelog entries with feature/issue reference for each change

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
