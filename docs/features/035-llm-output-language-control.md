# LLM Output Language Control

## Description

This feature adds an explicit output-language control for LLM-assisted Forge responses.

Goal:
- allow users to request LLM output in a specific language
- keep deterministic/evidence steps unchanged
- keep behavior explicit and auditable

## Spec

### CLI

New option:
- `--llm-output-language <value>`

Examples:
- `forge --llm-output-language de query "Where is pricing calculated?"`
- `forge --llm-output-language en explain src/mod.py`

### Config and env

New config key:
- `llm.prompt.output_language`

New env override:
- `FORGE_LLM_OUTPUT_LANGUAGE`

Precedence remains:
1. CLI
2. env
3. TOML
4. default (`auto`)

### Prompt behavior

- All LLM prompts carry the resolved output-language instruction.
- `auto` means: same language as user question.
- Query planner keeps canonical schema semantics:
  - `normalized_question_en` stays English
  - enum values remain canonical English
  - free-text planner fields follow output-language instruction where applicable

### Validation

Allowed:
- `auto`
- BCP-47-like tags (e.g. `de`, `en`, `de-DE`)

Invalid values produce explicit config validation errors.

## Definition of Done

- CLI supports `--llm-output-language`
- config/env resolution includes output language with precedence and validation
- all LLM prompt templates include output-language instruction
- LLM usage metadata exposes effective `output_language`
- docs include option and config examples

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 035; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
