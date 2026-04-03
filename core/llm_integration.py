"""Controlled LLM integration helpers for Forge capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from string import Template

from core.capability_model import Capability, Profile


class LLMInvocationPolicy(str):
    OFF = "off"
    OPTIONAL = "optional"
    PREFERRED = "preferred"


POLICY_MATRIX: dict[tuple[Capability, Profile], str] = {
    (Capability.QUERY, Profile.SIMPLE): LLMInvocationPolicy.OFF,
    (Capability.QUERY, Profile.STANDARD): LLMInvocationPolicy.OPTIONAL,
    (Capability.QUERY, Profile.DETAILED): LLMInvocationPolicy.OPTIONAL,
    (Capability.EXPLAIN, Profile.SIMPLE): LLMInvocationPolicy.OFF,
    (Capability.EXPLAIN, Profile.STANDARD): LLMInvocationPolicy.OPTIONAL,
    (Capability.EXPLAIN, Profile.DETAILED): LLMInvocationPolicy.PREFERRED,
    (Capability.REVIEW, Profile.SIMPLE): LLMInvocationPolicy.OFF,
    (Capability.REVIEW, Profile.STANDARD): LLMInvocationPolicy.OPTIONAL,
    (Capability.REVIEW, Profile.DETAILED): LLMInvocationPolicy.PREFERRED,
    (Capability.DESCRIBE, Profile.SIMPLE): LLMInvocationPolicy.OFF,
    (Capability.DESCRIBE, Profile.STANDARD): LLMInvocationPolicy.OPTIONAL,
    (Capability.DESCRIBE, Profile.DETAILED): LLMInvocationPolicy.OPTIONAL,
    (Capability.TEST, Profile.SIMPLE): LLMInvocationPolicy.OFF,
    (Capability.TEST, Profile.STANDARD): LLMInvocationPolicy.OPTIONAL,
    (Capability.TEST, Profile.DETAILED): LLMInvocationPolicy.PREFERRED,
}


@dataclass(frozen=True)
class LLMSettings:
    mode: str
    provider: str | None
    model: str | None


@dataclass
class LLMOutcome:
    summary: str
    usage: dict[str, object]
    uncertainty_notes: list[str]


def policy_for(capability: Capability, profile: Profile) -> str:
    return POLICY_MATRIX.get((capability, profile), LLMInvocationPolicy.OFF)


def resolve_settings(args) -> LLMSettings:
    provider = args.llm_provider or os.environ.get("FORGE_LLM_PROVIDER")
    model = args.llm_model or os.environ.get("FORGE_LLM_MODEL")
    if provider == "mock" and not model:
        model = "forge-mock-v1"
    return LLMSettings(mode=args.llm_mode, provider=provider, model=model)


def _template_path(capability: Capability) -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "llm" / f"{capability.value}.txt"


def _render_prompt(
    *,
    capability: Capability,
    profile: Profile,
    task: str,
    deterministic_summary: str,
    evidence: list[dict[str, object]],
) -> tuple[str | None, str | None]:
    path = _template_path(capability)
    if not path.exists():
        return None, f"missing prompt template: {path}"

    lines: list[str] = []
    for item in evidence[:12]:
        path_value = item.get("path", "?")
        line_value = item.get("line", "?")
        text = str(item.get("text", "")).strip()
        lines.append(f"- {path_value}:{line_value}: {text}")
    evidence_block = "\n".join(lines) if lines else "- no explicit evidence lines supplied"

    raw = path.read_text(encoding="utf-8")
    prompt = Template(raw).safe_substitute(
        capability=capability.value,
        profile=profile.value,
        task=task,
        deterministic_summary=deterministic_summary,
        evidence_block=evidence_block,
    )
    return prompt, None


def _mock_complete(
    *,
    capability: Capability,
    deterministic_summary: str,
    evidence: list[dict[str, object]],
) -> str:
    if not evidence:
        return deterministic_summary
    first_path = str(evidence[0].get("path", "repository"))
    if capability == Capability.REVIEW:
        return f"{deterministic_summary} Findings are anchored in concrete code evidence."
    return f"{deterministic_summary} Primary evidence anchor: {first_path}."


def maybe_refine_summary(
    *,
    capability: Capability,
    profile: Profile,
    task: str,
    deterministic_summary: str,
    evidence: list[dict[str, object]],
    settings: LLMSettings,
) -> LLMOutcome:
    policy = policy_for(capability, profile)
    usage: dict[str, object] = {
        "policy": policy,
        "mode": settings.mode,
        "provider": settings.provider,
        "model": settings.model,
        "attempted": False,
        "used": False,
        "fallback_reason": None,
        "prompt_template": str(_template_path(capability).relative_to(Path(__file__).resolve().parents[1])),
    }
    uncertainty_notes: list[str] = []

    if policy == LLMInvocationPolicy.OFF:
        usage["fallback_reason"] = "llm policy is off for this capability/profile"
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)

    if settings.mode == "off":
        usage["fallback_reason"] = "llm disabled by cli mode"
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)

    if settings.provider is None:
        usage["fallback_reason"] = "no llm provider configured"
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)

    usage["attempted"] = True
    prompt, prompt_error = _render_prompt(
        capability=capability,
        profile=profile,
        task=task,
        deterministic_summary=deterministic_summary,
        evidence=evidence,
    )
    if prompt_error:
        usage["fallback_reason"] = prompt_error
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)

    try:
        if settings.provider != "mock":
            raise RuntimeError(f"provider '{settings.provider}' is not configured in this build")
        _ = prompt  # prompt kept for explicit template usage/auditability
        refined = _mock_complete(
            capability=capability,
            deterministic_summary=deterministic_summary,
            evidence=evidence,
        )
        usage["used"] = True
        uncertainty_notes.append("Summary includes assistive LLM wording; verify nuanced interpretation manually.")
        return LLMOutcome(summary=refined, usage=usage, uncertainty_notes=uncertainty_notes)
    except Exception as exc:  # pragma: no cover - defensive fallback
        usage["fallback_reason"] = f"llm failure: {exc}"
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)


def provenance_section(*, llm_used: bool, evidence_count: int) -> dict[str, object]:
    return {
        "evidence_source": "repository_artifacts",
        "evidence_items": evidence_count,
        "inference_source": "deterministic_heuristics+llm" if llm_used else "deterministic_heuristics",
    }

