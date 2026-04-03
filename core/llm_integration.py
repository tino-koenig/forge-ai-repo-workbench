"""Controlled LLM integration helpers for Forge capabilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template
from urllib import error, request

from core.capability_model import Capability, Profile
from core.config import ResolvedLLMConfig, resolve_llm_config
from core.prompt_profiles import (
    default_prompt_profile,
    default_system_template_path,
    is_prompt_profile_allowed,
)


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


@dataclass
class LLMOutcome:
    summary: str
    usage: dict[str, object]
    uncertainty_notes: list[str]


def policy_for(capability: Capability, profile: Profile) -> str:
    return POLICY_MATRIX.get((capability, profile), LLMInvocationPolicy.OFF)


def resolve_settings(args, repo_root: Path) -> ResolvedLLMConfig:
    config = resolve_llm_config(args, repo_root)
    if config.provider == "mock" and not config.model:
        return ResolvedLLMConfig(
            mode=config.mode,
            provider=config.provider,
            base_url=config.base_url,
            model="forge-mock-v1",
            timeout_s=config.timeout_s,
            api_key_env=config.api_key_env,
            api_key=config.api_key,
            context_budget_tokens=config.context_budget_tokens,
            max_output_tokens=config.max_output_tokens,
            temperature=config.temperature,
            prompt_profile=config.prompt_profile,
            system_template_path=config.system_template_path,
            source=config.source,
            validation_error=config.validation_error,
        )
    return config


def _template_path(capability: Capability) -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "llm" / f"{capability.value}.txt"


def _render_prompt(
    *,
    capability: Capability,
    profile: Profile,
    task: str,
    deterministic_summary: str,
    evidence: list[dict[str, object]],
    context_budget_tokens: int,
) -> tuple[str | None, str | None]:
    path = _template_path(capability)
    if not path.exists():
        return None, f"missing prompt template: {path}"

    lines: list[str] = []
    char_budget = max(context_budget_tokens * 4, 800)
    used_chars = 0
    for item in evidence[:40]:
        path_value = item.get("path", "?")
        line_value = item.get("line", "?")
        text = str(item.get("text", "")).strip()
        candidate = f"- {path_value}:{line_value}: {text}"
        used_chars += len(candidate)
        if used_chars > char_budget:
            break
        lines.append(candidate)
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


def _load_system_prompt(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, f"missing system template: {path}"
    try:
        return path.read_text(encoding="utf-8").strip(), None
    except OSError as exc:
        return None, f"unable to read system template: {exc}"


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


def _openai_compatible_complete(
    *,
    settings: ResolvedLLMConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    if not settings.base_url:
        raise RuntimeError("missing base_url for openai_compatible provider")
    if not settings.model:
        raise RuntimeError("missing model for openai_compatible provider")
    if not settings.api_key:
        raise RuntimeError(f"missing API key from env var '{settings.api_key_env}'")

    base_url = settings.base_url.rstrip("/")
    if base_url.startswith("mock://"):
        return f"Refined via openai_compatible provider using model {settings.model}."
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_output_tokens,
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=settings.timeout_s) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc

    parsed = json.loads(raw)
    choices = parsed.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("openai-compatible response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("openai-compatible response choice malformed")
    message = first.get("message", {})
    if not isinstance(message, dict):
        raise RuntimeError("openai-compatible response message malformed")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("openai-compatible response missing content")
    return content.strip()


def maybe_refine_summary(
    *,
    capability: Capability,
    profile: Profile,
    task: str,
    deterministic_summary: str,
    evidence: list[dict[str, object]],
    settings: ResolvedLLMConfig,
) -> LLMOutcome:
    policy = policy_for(capability, profile)
    usage: dict[str, object] = {
        "policy": policy,
        "mode": settings.mode,
        "provider": settings.provider,
        "base_url": settings.base_url,
        "model": settings.model,
        "prompt_profile": settings.prompt_profile,
        "system_template": str(settings.system_template_path),
        "context_budget_tokens": settings.context_budget_tokens,
        "max_output_tokens": settings.max_output_tokens,
        "temperature": settings.temperature,
        "attempted": False,
        "used": False,
        "fallback_reason": None,
        "config_source": settings.source,
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
    if settings.validation_error:
        usage["fallback_reason"] = f"config validation error: {settings.validation_error}"
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)

    effective_profile = settings.prompt_profile
    effective_system_template = settings.system_template_path
    config_source = dict(settings.source)

    if settings.source.get("prompt_profile") == "default":
        effective_profile = default_prompt_profile(capability)
        config_source["prompt_profile"] = "capability_default"
    if not is_prompt_profile_allowed(capability, effective_profile):
        usage["fallback_reason"] = (
            f"prompt profile '{effective_profile}' not allowed for capability '{capability.value}'"
        )
        usage["config_source"] = config_source
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)

    if settings.source.get("system_template") == "default":
        effective_system_template = default_system_template_path(effective_profile)
        config_source["system_template"] = "profile_default"

    usage["prompt_profile"] = effective_profile
    usage["system_template"] = str(effective_system_template)
    usage["config_source"] = config_source

    usage["attempted"] = True
    prompt, prompt_error = _render_prompt(
        capability=capability,
        profile=profile,
        task=task,
        deterministic_summary=deterministic_summary,
        evidence=evidence,
        context_budget_tokens=settings.context_budget_tokens,
    )
    if prompt_error:
        usage["fallback_reason"] = prompt_error
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)
    system_prompt, system_error = _load_system_prompt(effective_system_template)
    if system_error:
        usage["fallback_reason"] = system_error
        return LLMOutcome(summary=deterministic_summary, usage=usage, uncertainty_notes=uncertainty_notes)
    assert system_prompt is not None

    try:
        if settings.provider == "mock":
            refined = _mock_complete(
                capability=capability,
                deterministic_summary=deterministic_summary,
                evidence=evidence,
            )
        elif settings.provider == "openai_compatible":
            refined = _openai_compatible_complete(
                settings=settings,
                system_prompt=system_prompt,
                user_prompt=prompt,
            )
        else:
            raise RuntimeError(f"provider '{settings.provider}' is not supported")
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
