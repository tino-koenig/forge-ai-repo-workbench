"""Controlled LLM integration helpers for Forge capabilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template
import time
from urllib import error, request

from core.capability_model import Capability, Profile
from core.config import ResolvedLLMConfig, resolve_llm_config
from core.llm_observability import log_llm_event
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


@dataclass
class QueryPlannerOutcome:
    search_terms: list[str]
    code_variants: list[str]
    normalized_question_en: str | None
    intent: str | None
    target_scope: str | None
    entity_types: list[str]
    dropped_filler_terms: list[str]
    usage: dict[str, object]


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
            query_planner_enabled=config.query_planner_enabled,
            query_planner_mode=config.query_planner_mode,
            query_planner_max_terms=config.query_planner_max_terms,
            query_planner_max_code_variants=config.query_planner_max_code_variants,
            query_planner_max_latency_ms=config.query_planner_max_latency_ms,
            observability_enabled=config.observability_enabled,
            observability_level=config.observability_level,
            observability_retention_count=config.observability_retention_count,
            observability_max_file_mb=config.observability_max_file_mb,
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
    timeout_s: float | None = None,
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
        with request.urlopen(req, timeout=timeout_s if timeout_s is not None else settings.timeout_s) as resp:
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


def _query_planner_template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "llm" / "query_planner.txt"


def _render_query_planner_prompt(
    *,
    question: str,
    source_language: str,
    deterministic_terms: list[str],
    settings: ResolvedLLMConfig,
) -> tuple[str | None, str | None]:
    path = _query_planner_template_path()
    if not path.exists():
        return None, f"missing prompt template: {path}"
    raw = path.read_text(encoding="utf-8")
    prompt = Template(raw).safe_substitute(
        question=question,
        source_language=source_language,
        deterministic_terms=", ".join(deterministic_terms[:16]),
        max_terms=str(settings.query_planner_max_terms),
        max_code_variants=str(settings.query_planner_max_code_variants),
    )
    return prompt, None


def _extract_json_object(raw_text: str) -> dict[str, object]:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("planner response does not contain a JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"planner JSON parse failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("planner response is not a JSON object")
    return parsed


def _sanitize_str_list(value: object, *, limit: int, min_len: int = 2, max_len: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = " ".join(item.strip().split())
        if len(candidate) < min_len or len(candidate) > max_len:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(candidate)
        if len(out) >= limit:
            break
    return out


def _sanitize_scope(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"code", "docs", "both"}:
        return normalized
    return None


def _sanitize_entity_types(value: object) -> list[str]:
    allowed = {"file", "module", "function", "class", "variable", "api_call", "config", "command_flag"}
    items = _sanitize_str_list(value, limit=8, min_len=2, max_len=32)
    result: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if normalized in allowed and normalized not in result:
            result.append(normalized)
    return result


def _mock_plan_query(question: str, deterministic_terms: list[str]) -> dict[str, object]:
    token_map = {
        "wo": "where",
        "wird": "is",
        "werden": "are",
        "preis": "price",
        "berechnet": "computed",
        "eintrittspunkt": "entrypoint",
        "haupt": "main",
        "welchen": "which",
        "dateien": "files",
        "eingesetzt": "used",
        "aufrufe": "calls",
        "aufruf": "call",
        "in": "in",
    }
    stop_de = {
        "in",
        "ein",
        "eine",
        "einen",
        "dem",
        "den",
        "der",
        "die",
        "das",
        "welchen",
        "wird",
        "werden",
        "gemacht",
    }
    stop_en = {"in", "the", "a", "an", "is", "are", "made", "used"}
    tokens = re.findall(r"[A-Za-z0-9_./-]+", question.lower())
    translated: list[str] = []
    for token in tokens:
        translated.append(token_map.get(token, token))
    normalized_question_en = " ".join(translated[:16]).strip() or question
    filtered = [t for t in translated if t not in stop_de and t not in stop_en and len(t) >= 3]
    target_scope = "both"
    entity_types = ["file", "module"]
    intent = "code_location_lookup"
    lowered = question.lower()
    if "llm" in lowered and any(marker in lowered for marker in ("aufruf", "call", "eingesetzt", "used")):
        intent = "llm_usage_locations"
        target_scope = "code"
        entity_types = ["api_call", "module", "function", "config"]
        filtered.extend(["openai", "chat/completions", "responses.create", "request.urlopen", "litellm"])

    deduped_terms: list[str] = []
    seen: set[str] = set()
    for term in [*deterministic_terms, *filtered]:
        normalized = term.strip().lower()
        if len(normalized) < 3 or normalized in seen:
            continue
        seen.add(normalized)
        deduped_terms.append(normalized)
    code_variants = ["openai_compatible_complete", "maybe_plan_query_terms"] if intent == "llm_usage_locations" else []
    return {
        "normalized_question_en": normalized_question_en,
        "intent": intent,
        "target_scope": target_scope,
        "entity_types": entity_types,
        "search_terms": deduped_terms[:10],
        "code_variants": code_variants[:4],
        "dropped_filler_terms": [token for token in tokens if token in {"bitte", "mal", "eigentlich", "kannst"}][:4],
    }


def maybe_plan_query_terms(
    *,
    capability: Capability,
    profile: Profile,
    question: str,
    source_language: str,
    deterministic_terms: list[str],
    settings: ResolvedLLMConfig,
    repo_root: Path | None = None,
) -> QueryPlannerOutcome:
    usage: dict[str, object] = {
        "enabled": settings.query_planner_enabled,
        "mode": settings.query_planner_mode,
        "attempted": False,
        "used": False,
        "provider": settings.provider,
        "model": settings.model,
        "prompt_template": str(_query_planner_template_path().relative_to(Path(__file__).resolve().parents[1])),
        "fallback_reason": None,
        "latency_ms": None,
        "source_language": source_language,
    }

    def _finish(
        *,
        search_terms: list[str],
        code_variants: list[str],
        normalized_question_en: str | None,
        intent: str | None,
        target_scope: str | None,
        entity_types: list[str],
        dropped_filler_terms: list[str],
    ) -> QueryPlannerOutcome:
        outcome = QueryPlannerOutcome(
            search_terms=search_terms,
            code_variants=code_variants,
            normalized_question_en=normalized_question_en,
            intent=intent,
            target_scope=target_scope,
            entity_types=entity_types,
            dropped_filler_terms=dropped_filler_terms,
            usage=usage,
        )
        log_llm_event(
            repo_root=repo_root,
            settings=settings,
            capability=capability,
            profile=profile,
            stage="query_planner",
            task=question,
            usage=usage,
            extra={
                "source_language": source_language,
                "search_terms_count": len(search_terms),
                "code_variants_count": len(code_variants),
                "target_scope": target_scope,
                "entity_types": entity_types,
            },
        )
        return outcome
    if not settings.query_planner_enabled or settings.query_planner_mode == "off":
        usage["fallback_reason"] = "query planner disabled by config"
        return _finish(
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )
    if settings.mode == "off":
        usage["fallback_reason"] = "llm disabled by cli mode"
        return _finish(
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )
    if settings.provider is None:
        usage["fallback_reason"] = "no llm provider configured"
        return _finish(
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )
    if settings.validation_error:
        usage["fallback_reason"] = f"config validation error: {settings.validation_error}"
        return _finish(
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )

    usage["attempted"] = True
    prompt, prompt_error = _render_query_planner_prompt(
        question=question,
        source_language=source_language,
        deterministic_terms=deterministic_terms,
        settings=settings,
    )
    if prompt_error:
        usage["fallback_reason"] = prompt_error
        return _finish(
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )
    assert prompt is not None

    started = time.perf_counter()
    try:
        if settings.provider == "mock":
            raw_result = _mock_plan_query(question, deterministic_terms)
        elif settings.provider == "openai_compatible":
            if (settings.base_url or "").startswith("mock://"):
                raw_result = _mock_plan_query(question, deterministic_terms)
            else:
                system_prompt, system_error = _load_system_prompt(settings.system_template_path)
                if system_error:
                    raise RuntimeError(system_error)
                assert system_prompt is not None
                timeout_s = min(settings.timeout_s, max(settings.query_planner_max_latency_ms / 1000.0, 0.2))
                text = _openai_compatible_complete(
                    settings=settings,
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    timeout_s=timeout_s,
                )
                raw_result = _extract_json_object(text)
        else:
            raise RuntimeError(f"provider '{settings.provider}' is not supported")
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage["latency_ms"] = latency_ms
        if latency_ms > settings.query_planner_max_latency_ms:
            usage["fallback_reason"] = (
                f"planner latency {latency_ms}ms exceeds max {settings.query_planner_max_latency_ms}ms"
            )
            return _finish(
                search_terms=[],
                code_variants=[],
                normalized_question_en=None,
                intent=None,
                target_scope=None,
                entity_types=[],
                dropped_filler_terms=[],
            )

        normalized_question_en = raw_result.get("normalized_question_en")
        intent = raw_result.get("intent")
        target_scope = _sanitize_scope(raw_result.get("target_scope"))
        entity_types = _sanitize_entity_types(raw_result.get("entity_types"))
        search_terms = _sanitize_str_list(raw_result.get("search_terms"), limit=settings.query_planner_max_terms)
        code_variants = _sanitize_str_list(
            raw_result.get("code_variants"),
            limit=settings.query_planner_max_code_variants,
            min_len=1,
            max_len=120,
        )
        dropped_filler_terms = _sanitize_str_list(raw_result.get("dropped_filler_terms"), limit=12, min_len=1)
        if not isinstance(normalized_question_en, str) or not normalized_question_en.strip():
            normalized_question_en = None
        if not isinstance(intent, str) or not intent.strip():
            intent = None

        if not search_terms and not code_variants:
            usage["fallback_reason"] = "planner output did not contain usable terms"
            return _finish(
                search_terms=[],
                code_variants=[],
                normalized_question_en=normalized_question_en,
                intent=intent,
                target_scope=target_scope,
                entity_types=entity_types,
                dropped_filler_terms=dropped_filler_terms,
            )
        usage["used"] = True
        return _finish(
            search_terms=search_terms,
            code_variants=code_variants,
            normalized_question_en=normalized_question_en,
            intent=intent,
            target_scope=target_scope,
            entity_types=entity_types,
            dropped_filler_terms=dropped_filler_terms,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        usage["latency_ms"] = int((time.perf_counter() - started) * 1000)
        usage["fallback_reason"] = f"planner failure: {exc}"
        return _finish(
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )


def maybe_refine_summary(
    *,
    capability: Capability,
    profile: Profile,
    task: str,
    deterministic_summary: str,
    evidence: list[dict[str, object]],
    settings: ResolvedLLMConfig,
    repo_root: Path | None = None,
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

    def _finish(summary: str) -> LLMOutcome:
        outcome = LLMOutcome(summary=summary, usage=usage, uncertainty_notes=uncertainty_notes)
        log_llm_event(
            repo_root=repo_root,
            settings=settings,
            capability=capability,
            profile=profile,
            stage="summary_refinement",
            task=task,
            usage=usage,
            extra={
                "evidence_count": len(evidence),
                "policy": policy,
            },
        )
        return outcome

    if policy == LLMInvocationPolicy.OFF:
        usage["fallback_reason"] = "llm policy is off for this capability/profile"
        return _finish(deterministic_summary)

    if settings.mode == "off":
        usage["fallback_reason"] = "llm disabled by cli mode"
        return _finish(deterministic_summary)

    if settings.provider is None:
        usage["fallback_reason"] = "no llm provider configured"
        return _finish(deterministic_summary)
    if settings.validation_error:
        usage["fallback_reason"] = f"config validation error: {settings.validation_error}"
        return _finish(deterministic_summary)

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
        return _finish(deterministic_summary)

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
        return _finish(deterministic_summary)
    system_prompt, system_error = _load_system_prompt(effective_system_template)
    if system_error:
        usage["fallback_reason"] = system_error
        return _finish(deterministic_summary)
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
        return _finish(refined)
    except Exception as exc:  # pragma: no cover - defensive fallback
        usage["fallback_reason"] = f"llm failure: {exc}"
        return _finish(deterministic_summary)


def provenance_section(*, llm_used: bool, evidence_count: int) -> dict[str, object]:
    return {
        "evidence_source": "repository_artifacts",
        "evidence_items": evidence_count,
        "inference_source": "deterministic_heuristics+llm" if llm_used else "deterministic_heuristics",
    }
