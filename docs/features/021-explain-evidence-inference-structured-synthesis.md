# Explain Evidence/Inference Structured Synthesis

## Description

This feature improves `forge explain` output quality by enforcing a strict structure:
- evidence
- inference
- uncertainty/confidence

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

Text output should mirror the same structure in concise sections.

### Safety and transparency

- no write effects
- no hidden chain-of-thought exposure
- confidence claims must be linked to visible evidence density/signals

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
