# Explain Evidence/Inference Structured Synthesis

## Description

This feature improves `forge explain` output quality by enforcing explicit separation between:
- evidence (what is directly observable)
- inference (what is interpreted from evidence)
- uncertainty/confidence (how certain the interpretation is)

LLM is used only for synthesis and clarity, not for evidence discovery.

## Spec

### Scope

Upgrade explain pipeline to explicit stages:
1. deterministic target resolution
2. deterministic evidence extraction
3. optional LLM synthesis constrained by evidence
4. structured output assembly

### Structured synthesis contract

Explain output must include:
- `evidence_facts`: direct file/line grounded observations
- `inference_points`: interpreted meaning derived from facts
- `confidence`: per inference level (`high|medium|low`) with rationale
- `uncertainty_notes`: explicit limitations

### Capability behavior

LLM synthesis rules:
- may rephrase and summarize
- may connect evidence points into role explanation
- may not introduce symbols/files absent from evidence context
- must emit uncertainty when evidence is sparse

Fallback:
- deterministic explain path remains complete and usable
- fallback reason is reported

### Profile behavior

- simple: deterministic structure, no LLM synthesis
- standard: optional LLM synthesis
- detailed: preferred LLM synthesis with richer rationale section

### Output changes

Add explain JSON sections:
- `evidence_facts`
- `inference_points`
- `confidence`
- `role_hypothesis_alternatives` (detailed profile)

Text output requirements:
- `standard` view stays human-first and concise (no verbose contract dump)
- `full` view mirrors the structured sections in readable blocks
- `compact` keeps only a compressed summary + top evidence anchors

### Safety and transparency

- no write effects
- no hidden chain-of-thought exposure
- confidence claims must be linked to visible evidence density/signals

### Alignment with current Forge direction

- This feature extends existing explain behavior; it does not replace human-first defaults.
- Structured richness is primarily guaranteed in JSON contracts.
- Text mode remains optimized for readability first, with deeper structure in `full`.
- No effect-boundary changes: capability remains read-only.

## Design

### Why this feature

Users need stronger explain quality, but still auditable and grounded.
Separating evidence from inference makes LLM value visible and safer.

### Non-goals

- no architecture graph generation in this feature
- no autonomous refactoring suggestions

## Definition of Done

- explain outputs are consistently split into evidence/inference/confidence
- LLM synthesis improves clarity while preserving grounding constraints
- fallback path remains deterministic and explicit
- quality gates verify:
  - no fabricated file references
  - inference always backed by at least one evidence anchor
  - contract shape for explain structured sections
  - text `standard` view remains concise and human-first

## Implemented Behavior (Current)

- Implementation status: implemented.
- Traceability: `CHANGELOG.md` references feature 021; status and notes are indexed in `docs/status/features-index.md`.
- This addendum summarizes runtime availability; the normative intent remains in the spec sections above.

## How To Validate Quickly

- Run `forge --help` to confirm command surface is available.
- Run the relevant capability command(s) for this feature in a repository context.
- Use `python3 scripts/run_quality_gates.py` for regression-oriented validation when behavior changes.

## Known Limits / Notes

- For detailed constraints and non-goals, rely on the original spec content above.
- When implementation behavior diverges, update this addendum together with `CHANGELOG.md`.
