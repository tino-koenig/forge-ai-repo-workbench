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
    lead_terms: list[str]
    support_terms: list[str]
    search_terms: list[str]
    code_variants: list[str]
    normalized_question_en: str | None
    intent: str | None
    target_scope: str | None
    entity_types: list[str]
    dropped_filler_terms: list[str]
    usage: dict[str, object]


LEAD_TERM_GENERIC_EXCLUSIONS = {
    "code",
    "location",
    "where",
    "what",
    "which",
    "find",
    "show",
    "entry",
    "source",
    "file",
    "files",
    "module",
    "class",
    "function",
    "variable",
    "api",
    "api_call",
    "config",
    "defined",
    "declaration",
    "implementation",
    "is",
    "are",
    "ist",
    "wo",
    "was",
    "wie",
}


@dataclass
class QueryActionDecision:
    decision: str
    next_action: str | None
    reason: str
    confidence: str


@dataclass
class QueryActionOrchestrationOutcome:
    decisions: list[QueryActionDecision]
    done_reason: str
    usage: dict[str, object]
    fallback_reason: str | None


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
            output_language=config.output_language,
            prompt_profile=config.prompt_profile,
            system_template_path=config.system_template_path,
            query_planner_enabled=config.query_planner_enabled,
            query_planner_mode=config.query_planner_mode,
            query_planner_max_terms=config.query_planner_max_terms,
            query_planner_max_code_variants=config.query_planner_max_code_variants,
            query_planner_max_latency_ms=config.query_planner_max_latency_ms,
            query_orchestrator_enabled=config.query_orchestrator_enabled,
            query_orchestrator_mode=config.query_orchestrator_mode,
            query_orchestrator_max_iterations=config.query_orchestrator_max_iterations,
            query_orchestrator_max_files=config.query_orchestrator_max_files,
            query_orchestrator_max_tokens=config.query_orchestrator_max_tokens,
            query_orchestrator_max_wall_time_ms=config.query_orchestrator_max_wall_time_ms,
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
    output_language_instruction: str,
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
        output_language_instruction=output_language_instruction,
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
    if capability == Capability.QUERY:
        return json.dumps(
            {
                "preserved_summary": deterministic_summary,
                "style_addendum": f"Primary evidence anchor: {first_path}.",
            },
            ensure_ascii=False,
        )
    return f"{deterministic_summary} Primary evidence anchor: {first_path}."


def _refinement_contradicts_deterministic_query_summary(*, deterministic_summary: str, refined_summary: str) -> bool:
    deterministic_lower = deterministic_summary.strip().lower()
    refined_lower = refined_summary.strip().lower()
    if not deterministic_lower or not refined_lower:
        return False
    if not deterministic_lower.startswith("most likely relevant files:"):
        return False

    contradiction_markers = (
        "nicht gefunden",
        "nicht direkt ersichtlich",
        "nicht ersichtlich",
        "keine hinweise",
        "keine expliziten hinweise",
        "keine treffer",
        "not found",
        "not directly apparent",
        "not apparent",
        "no evidence",
        "no explicit evidence",
        "no matches",
    )
    if any(marker in refined_lower for marker in contradiction_markers):
        return True

    # Keep deterministic location anchors authoritative in query mode.
    # If the refinement drops all top deterministic paths, treat it as contradiction/noise.
    summary_body = deterministic_summary.strip()
    colon_idx = summary_body.find(":")
    if colon_idx == -1:
        return False
    path_part = summary_body[colon_idx + 1 :].strip().rstrip(".")
    top_paths = [item.strip().lower() for item in path_part.split(",") if item.strip()]
    if not top_paths:
        return False
    if not any(path in refined_lower for path in top_paths[:3]):
        return True
    return False


def _normalize_text_for_containment(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _refinement_preserves_deterministic_summary(*, deterministic_summary: str, refined_summary: str) -> bool:
    base = _normalize_text_for_containment(deterministic_summary)
    refined = _normalize_text_for_containment(refined_summary)
    if not base:
        return True
    return base in refined


def _sanitize_single_sentence(value: object, *, max_len: int = 220) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = " ".join(value.strip().split())
    if not candidate:
        return None
    if len(candidate) > max_len:
        candidate = candidate[:max_len].rstrip()
    return candidate


def _parse_query_refinement_response(
    *,
    raw_response: str,
    deterministic_summary: str,
) -> tuple[str | None, str | None]:
    try:
        parsed = _extract_json_object(raw_response)
    except RuntimeError as exc:
        return None, f"query refinement JSON parse failed: {exc}"

    preserved = parsed.get("preserved_summary")
    if not isinstance(preserved, str):
        return None, "query refinement missing preserved_summary"
    if preserved != deterministic_summary:
        return None, "query refinement altered preserved_summary"

    # Query refinement is wording-only and must not introduce new factual claims.
    # Keep deterministic summary as authoritative output even if optional addendum is present.
    return deterministic_summary, None


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


def _query_action_orchestrator_template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "llm" / "query_action_orchestrator.txt"


def _render_query_planner_prompt(
    *,
    question: str,
    source_language: str,
    deterministic_terms: list[str],
    settings: ResolvedLLMConfig,
    output_language_instruction: str,
) -> tuple[str | None, str | None]:
    path = _query_planner_template_path()
    if not path.exists():
        return None, f"missing prompt template: {path}"
    raw = path.read_text(encoding="utf-8")
    prompt = Template(raw).safe_substitute(
        question=question,
        source_language=source_language,
        output_language_instruction=output_language_instruction,
        deterministic_terms=", ".join(deterministic_terms[:16]),
        max_terms=str(settings.query_planner_max_terms),
        max_code_variants=str(settings.query_planner_max_code_variants),
    )
    return prompt, None


def _render_query_action_orchestrator_prompt(
    *,
    question: str,
    candidate_paths: list[str],
    evidence_count: int,
    iteration: int,
    max_iterations: int,
    max_files: int,
    max_tokens: int,
    max_wall_time_ms: int,
) -> tuple[str | None, str | None]:
    path = _query_action_orchestrator_template_path()
    if not path.exists():
        return None, f"missing prompt template: {path}"
    raw = path.read_text(encoding="utf-8")
    prompt = Template(raw).safe_substitute(
        question=question,
        candidate_paths=", ".join(candidate_paths[:10]),
        evidence_count=str(evidence_count),
        iteration=str(iteration),
        max_iterations=str(max_iterations),
        max_files=str(max_files),
        max_tokens=str(max_tokens),
        max_wall_time_ms=str(max_wall_time_ms),
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


def _normalize_planner_priority_buckets(
    lead_terms: list[str],
    support_terms: list[str],
    search_terms: list[str],
) -> tuple[list[str], list[str], list[str]]:
    # Keep lead terms focused on concrete anchors.
    normalized_lead: list[str] = []
    demoted: list[str] = []
    for term in lead_terms:
        base = term.strip().lower()
        if base in LEAD_TERM_GENERIC_EXCLUSIONS:
            demoted.append(term)
            continue
        normalized_lead.append(term)

    support_raw = [*support_terms, *demoted]
    normalized_support: list[str] = []
    seen_support: set[str] = set()
    for term in support_raw:
        base = term.strip().lower()
        if not base or base in seen_support:
            continue
        seen_support.add(base)
        normalized_support.append(term)

    if not normalized_lead and normalized_support:
        normalized_lead.append(normalized_support[0])
        normalized_support = normalized_support[1:]

    search_raw = search_terms if search_terms else [*normalized_lead, *normalized_support]
    normalized_search: list[str] = []
    seen_search: set[str] = set()
    for term in search_raw:
        base = term.strip().lower()
        if not base or base in seen_search:
            continue
        seen_search.add(base)
        normalized_search.append(term)
    return normalized_lead, normalized_support, normalized_search


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
    lead_terms = deduped_terms[:2]
    support_terms = deduped_terms[2:10]
    return {
        "normalized_question_en": normalized_question_en,
        "intent": intent,
        "target_scope": target_scope,
        "entity_types": entity_types,
        "lead_terms": lead_terms,
        "support_terms": support_terms,
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
        "output_language": settings.output_language,
    }

    def _finish(
        *,
        lead_terms: list[str],
        support_terms: list[str],
        search_terms: list[str],
        code_variants: list[str],
        normalized_question_en: str | None,
        intent: str | None,
        target_scope: str | None,
        entity_types: list[str],
        dropped_filler_terms: list[str],
    ) -> QueryPlannerOutcome:
        outcome = QueryPlannerOutcome(
            lead_terms=lead_terms,
            support_terms=support_terms,
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
            lead_terms=[],
            support_terms=[],
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
            lead_terms=[],
            support_terms=[],
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
            lead_terms=[],
            support_terms=[],
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
            lead_terms=[],
            support_terms=[],
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )

    usage["attempted"] = True
    output_language_instruction = (
        "same language as the user question"
        if settings.output_language == "auto"
        else settings.output_language
    )
    prompt, prompt_error = _render_query_planner_prompt(
        question=question,
        source_language=source_language,
        deterministic_terms=deterministic_terms,
        settings=settings,
        output_language_instruction=output_language_instruction,
    )
    if prompt_error:
        usage["fallback_reason"] = prompt_error
        return _finish(
            lead_terms=[],
            support_terms=[],
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
                lead_terms=[],
                support_terms=[],
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
        lead_terms = _sanitize_str_list(raw_result.get("lead_terms"), limit=settings.query_planner_max_terms)
        support_terms = _sanitize_str_list(raw_result.get("support_terms"), limit=settings.query_planner_max_terms)
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

        # Backward/partial compatibility:
        # If planner does not provide prioritized buckets, derive them from search_terms.
        if not lead_terms and search_terms:
            lead_terms = search_terms[:2]
        if not support_terms and search_terms:
            support_terms = [term for term in search_terms if term not in set(lead_terms)]
        if not search_terms and (lead_terms or support_terms):
            search_terms = [*lead_terms, *support_terms]
            search_terms = _sanitize_str_list(search_terms, limit=settings.query_planner_max_terms)
        lead_terms, support_terms, search_terms = _normalize_planner_priority_buckets(
            lead_terms,
            support_terms,
            search_terms,
        )
        lead_terms = _sanitize_str_list(lead_terms, limit=settings.query_planner_max_terms)
        support_terms = _sanitize_str_list(support_terms, limit=settings.query_planner_max_terms)
        search_terms = _sanitize_str_list(search_terms, limit=settings.query_planner_max_terms)

        if not search_terms and not code_variants:
            usage["fallback_reason"] = "planner output did not contain usable terms"
            return _finish(
                lead_terms=lead_terms,
                support_terms=support_terms,
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
            lead_terms=lead_terms,
            support_terms=support_terms,
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
            lead_terms=[],
            support_terms=[],
            search_terms=[],
            code_variants=[],
            normalized_question_en=None,
            intent=None,
            target_scope=None,
            entity_types=[],
            dropped_filler_terms=[],
        )


def maybe_orchestrate_query_actions(
    *,
    capability: Capability,
    profile: Profile,
    question: str,
    candidate_paths: list[str],
    evidence_count: int,
    iteration: int = 1,
    settings: ResolvedLLMConfig,
    repo_root: Path | None = None,
) -> QueryActionOrchestrationOutcome:
    action_catalog = ["search", "read", "explain", "rank", "summarize", "stop"]
    usage: dict[str, object] = {
        "enabled": settings.query_orchestrator_enabled,
        "mode": settings.query_orchestrator_mode,
        "attempted": False,
        "used": False,
        "provider": settings.provider,
        "model": settings.model,
        "prompt_template": str(_query_action_orchestrator_template_path().relative_to(Path(__file__).resolve().parents[1])),
        "latency_ms": None,
        "fallback_reason": None,
        "max_iterations": settings.query_orchestrator_max_iterations,
        "max_files": settings.query_orchestrator_max_files,
        "max_tokens": settings.query_orchestrator_max_tokens,
        "max_wall_time_ms": settings.query_orchestrator_max_wall_time_ms,
        "catalog": action_catalog,
        "iteration": iteration,
    }
    decisions: list[QueryActionDecision] = []

    def _finish(done_reason: str, fallback_reason: str | None = None) -> QueryActionOrchestrationOutcome:
        if fallback_reason:
            usage["fallback_reason"] = fallback_reason
        log_llm_event(
            repo_root=repo_root,
            settings=settings,
            capability=capability,
            profile=profile,
            stage="query_action_orchestrator",
            task=question,
            usage=usage,
            extra={
                "done_reason": done_reason,
                "decision_count": len(decisions),
                "candidate_count": len(candidate_paths),
                "evidence_count": evidence_count,
            },
        )
        return QueryActionOrchestrationOutcome(
            decisions=decisions,
            done_reason=done_reason,
            usage=usage,
            fallback_reason=fallback_reason,
        )

    if not settings.query_orchestrator_enabled or settings.query_orchestrator_mode == "off":
        return _finish("sufficient_evidence", "query action orchestrator disabled by config")
    if settings.mode == "off":
        return _finish("sufficient_evidence", "llm disabled by cli mode")
    if settings.provider is None:
        return _finish("sufficient_evidence", "no llm provider configured")
    if settings.validation_error:
        return _finish("policy_blocked", f"config validation error: {settings.validation_error}")

    usage["attempted"] = True
    started = time.perf_counter()
    try:
        raw_result: dict[str, object]
        if settings.provider == "mock":
            raw_result = {
                "decision": "stop" if evidence_count >= 5 else "continue",
                "next_action": None if evidence_count >= 5 else "read",
                "reason": "sufficient evidence for summary" if evidence_count >= 5 else "need a bit more direct evidence",
                "confidence": "high" if evidence_count >= 5 else "medium",
            }
        elif settings.provider == "openai_compatible":
            prompt, prompt_error = _render_query_action_orchestrator_prompt(
                question=question,
                candidate_paths=candidate_paths,
                evidence_count=evidence_count,
                iteration=iteration,
                max_iterations=settings.query_orchestrator_max_iterations,
                max_files=settings.query_orchestrator_max_files,
                max_tokens=settings.query_orchestrator_max_tokens,
                max_wall_time_ms=settings.query_orchestrator_max_wall_time_ms,
            )
            if prompt_error:
                return _finish("policy_blocked", prompt_error)
            assert prompt is not None
            if (settings.base_url or "").startswith("mock://"):
                raw_result = {
                    "decision": "stop" if evidence_count >= 5 else "continue",
                    "next_action": None if evidence_count >= 5 else "read",
                    "reason": "mock orchestration decision",
                    "confidence": "medium",
                }
            else:
                system_prompt, system_error = _load_system_prompt(settings.system_template_path)
                if system_error:
                    return _finish("policy_blocked", system_error)
                assert system_prompt is not None
                timeout_s = min(settings.timeout_s, max(settings.query_orchestrator_max_wall_time_ms / 1000.0, 0.2))
                raw = _openai_compatible_complete(
                    settings=settings,
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    timeout_s=timeout_s,
                )
                raw_result = _extract_json_object(raw)
        else:
            return _finish("policy_blocked", f"provider '{settings.provider}' is not supported")

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage["latency_ms"] = latency_ms
        if latency_ms > settings.query_orchestrator_max_wall_time_ms:
            return _finish(
                "budget_exhausted",
                f"orchestrator latency {latency_ms}ms exceeds max {settings.query_orchestrator_max_wall_time_ms}ms",
            )

        decision = str(raw_result.get("decision", "")).strip().lower()
        next_action_raw = raw_result.get("next_action")
        next_action = str(next_action_raw).strip().lower() if isinstance(next_action_raw, str) else None
        reason = str(raw_result.get("reason", "")).strip()
        confidence = str(raw_result.get("confidence", "")).strip().lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        if decision not in {"continue", "stop"}:
            return _finish("policy_blocked", f"invalid orchestration decision '{decision}'")
        if decision == "continue":
            if next_action is None:
                return _finish("policy_blocked", "orchestration continue decision missing next_action")
            if next_action not in action_catalog or next_action == "stop":
                return _finish("policy_blocked", f"orchestration next_action '{next_action}' is not allowed")
        else:
            next_action = None
        decisions.append(
            QueryActionDecision(
                decision=decision,
                next_action=next_action,
                reason=reason or "no reason provided",
                confidence=confidence,
            )
        )
        usage["used"] = True
        if decision == "stop":
            return _finish("sufficient_evidence")
        return _finish("sufficient_evidence")
    except Exception as exc:  # pragma: no cover - defensive fallback
        usage["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return _finish("policy_blocked", f"orchestrator failure: {exc}")


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
        "output_language": settings.output_language,
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
    output_language_instruction = (
        "same language as the user question"
        if settings.output_language == "auto"
        else settings.output_language
    )
    prompt, prompt_error = _render_prompt(
        capability=capability,
        profile=profile,
        task=task,
        deterministic_summary=deterministic_summary,
        evidence=evidence,
        context_budget_tokens=settings.context_budget_tokens,
        output_language_instruction=output_language_instruction,
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
        if capability == Capability.QUERY:
            refined_query_summary, query_refinement_error = _parse_query_refinement_response(
                raw_response=refined,
                deterministic_summary=deterministic_summary,
            )
            if query_refinement_error:
                usage["fallback_reason"] = query_refinement_error
                uncertainty_notes.append(
                    "Discarded LLM query refinement because it violated the strict summary-preservation JSON contract."
                )
                return _finish(deterministic_summary)
            assert refined_query_summary is not None
            refined = refined_query_summary
        if capability == Capability.QUERY and not _refinement_preserves_deterministic_summary(
            deterministic_summary=deterministic_summary,
            refined_summary=refined,
        ):
            usage["fallback_reason"] = "refinement did not preserve deterministic summary"
            uncertainty_notes.append(
                "Discarded LLM summary rewrite because it changed deterministic core claims instead of only rephrasing."
            )
            return _finish(deterministic_summary)
        if capability == Capability.QUERY and _refinement_contradicts_deterministic_query_summary(
            deterministic_summary=deterministic_summary,
            refined_summary=refined,
        ):
            usage["fallback_reason"] = "refinement contradicted deterministic query summary"
            uncertainty_notes.append("Discarded LLM summary rewrite because it contradicted deterministic file evidence.")
            return _finish(deterministic_summary)
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
