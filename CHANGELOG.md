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
