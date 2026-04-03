from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import load_index_entry_map, load_index_path_class_map, path_class_weight
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import (
    maybe_orchestrate_query_actions,
    maybe_plan_query_terms,
    maybe_refine_summary,
    provenance_section,
    resolve_settings,
)
from core.mode_capability_contract import evaluate_action_eligibility
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.repo_io import iter_repo_files, read_text_file


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "where",
    "which",
    "who",
    "why",
    "with",
}

STOP_WORDS_DE = {
    "in",
    "im",
    "am",
    "an",
    "den",
    "dem",
    "der",
    "die",
    "das",
    "ein",
    "eine",
    "einen",
    "welchen",
    "welche",
    "werden",
    "wird",
    "gemacht",
    "dateien",
}

GENERIC_QUERY_TERMS = {
    "find",
    "entry",
    "point",
    "main",
    "show",
    "where",
    "which",
}

ENTRYPOINT_PHRASES = {
    "main entry point",
    "entry point",
    "entrypoint",
}

ENTRYPOINT_PATH_HINTS = {
    "forge.py",
    "__main__.py",
    "main.py",
    "cmd/cli.py",
}

ENTRYPOINT_LINE_HINTS = (
    "__main__",
    "argparse.argumentparser(",
    "entry_points",
    "def main(",
    "raise systemexit(main(",
)

LLM_CALL_LINE_HINTS = (
    "chat/completions",
    "chat.completions",
    "responses.create",
    "request.urlopen(",
    "authorization",
    "openai_compatible",
    "base_url",
)

LANGUAGE_HINTS_DE = {
    "wo",
    "wie",
    "welche",
    "finde",
    "finden",
    "suche",
    "eintrittspunkt",
    "haupt",
    "berechnet",
    "berechnung",
    "preis",
    "datei",
    "dateien",
    "funktion",
    "welchen",
    "werden",
    "gemacht",
    "aufrufe",
    "welcher",
}

LANGUAGE_HINTS_EN = {
    "where",
    "which",
    "file",
    "files",
    "find",
    "call",
    "calls",
    "made",
    "entry",
    "point",
    "main",
}

WRITE_REQUEST_HINTS = {
    "fix",
    "edit",
    "change",
    "rewrite",
    "update",
    "patch",
    "implement",
    "refactor",
    "delete",
    "remove",
    "replace",
    "schreib",
    "aender",
    "ändere",
    "anpassen",
    "lösch",
    "loesch",
    "ersetz",
    "korrigier",
    "fixe",
    "implementier",
    "refaktor",
}

DE_TO_EN_TERM_MAP = {
    "eintrittspunkt": "entrypoint",
    "haupt": "main",
    "hauptpunkt": "main",
    "preis": "price",
    "berechnet": "calculate",
    "berechnung": "calculation",
    "funktion": "function",
    "datei": "file",
    "klasse": "class",
    "test": "test",
    "tests": "tests",
    "wo": "where",
    "finde": "find",
    "finden": "find",
    "aufruf": "call",
    "aufrufe": "calls",
    "llm-aufrufe": "llm calls",
    "llm": "llm",
}

EN_TO_DE_TERM_MAP = {
    "entrypoint": "eintrittspunkt",
    "main": "haupt",
    "price": "preis",
    "calculate": "berechnet",
    "function": "funktion",
    "file": "datei",
    "class": "klasse",
}


@dataclass
class Evidence:
    line: int
    text: str
    term: str


@dataclass
class Candidate:
    path: Path
    evidences: list[Evidence]
    score: int
    path_class: str


@dataclass
class CrossLingualExpansion:
    source_language: str
    mapped_terms: list[dict[str, str]]
    expansion_mode: str


@dataclass
class ExplainFeedback:
    path: Path
    intent_match: bool
    evidence_density: float
    linkage_confidence: str
    relevance_score: int
    rationale: list[str]


def normalize_question(question: str) -> str:
    return " ".join(question.strip().split())


def detect_language(question: str) -> str:
    lowered = normalize_question(question).lower()
    if re.search(r"[äöüß]", lowered):
        return "de"
    tokens = re.findall(r"[A-Za-z0-9_./-]+", lowered)
    if not tokens:
        return "unknown"
    expanded_tokens: list[str] = []
    for token in tokens:
        expanded_tokens.append(token)
        expanded_tokens.extend(part for part in re.split(r"[-_/]", token) if part)
    tokens = expanded_tokens
    de_hits = sum(1 for token in tokens if token in LANGUAGE_HINTS_DE)
    en_hits = sum(1 for token in tokens if token in LANGUAGE_HINTS_EN)
    if de_hits >= 2 and de_hits >= en_hits:
        return "de"
    if en_hits >= 2 and en_hits > de_hits:
        return "en"
    if de_hits > en_hits:
        return "de"
    if en_hits > de_hits:
        return "en"
    return "en"


def build_cross_lingual_expansion(question: str, profile: Profile) -> CrossLingualExpansion:
    source_language = detect_language(question)
    raw_tokens = re.findall(r"[A-Za-z0-9_./-]+", normalize_question(question).lower())
    tokens: list[str] = []
    for raw in raw_tokens:
        tokens.append(raw)
        tokens.extend(part for part in re.split(r"[-_/]", raw) if part)
    mapped_terms: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    mapping = {}
    if source_language == "de":
        mapping = DE_TO_EN_TERM_MAP
    elif source_language == "en":
        mapping = EN_TO_DE_TERM_MAP

    max_items = 2 if profile == Profile.SIMPLE else 4 if profile == Profile.STANDARD else 6
    for token in tokens:
        mapped = mapping.get(token)
        if not mapped:
            continue
        pair = (token, mapped)
        if pair in seen:
            continue
        seen.add(pair)
        mapped_terms.append({"source_term": token, "mapped_term": mapped})
        if len(mapped_terms) >= max_items:
            break

    return CrossLingualExpansion(
        source_language=source_language,
        mapped_terms=mapped_terms,
        expansion_mode="deterministic" if mapped_terms else "none",
    )


def derive_search_terms(
    question: str,
    profile: Profile,
    cross_lingual: CrossLingualExpansion,
    planner_terms: list[str] | None = None,
    planner_code_variants: list[str] | None = None,
) -> list[str]:
    quoted_phrases = re.findall(r'"([^"]+)"', question)
    word_tokens = re.findall(r"[A-Za-z0-9_./-]+", question.lower())
    filtered_words: list[str] = []
    for token in word_tokens:
        parts = [token, *[p for p in re.split(r"[-_/]", token) if p]]
        for part in parts:
            if len(part) < 3:
                continue
            if part in STOP_WORDS or part in STOP_WORDS_DE:
                continue
            filtered_words.append(part)

    terms: list[str] = []
    normalized_question = normalize_question(question)
    if normalized_question:
        terms.append(normalized_question.lower())
    terms.extend([phrase.strip().lower() for phrase in quoted_phrases if phrase.strip()])
    terms.extend(filtered_words)
    terms.extend(item["mapped_term"] for item in cross_lingual.mapped_terms)
    terms.extend([item.lower() for item in (planner_terms or [])])
    terms.extend([item.lower() for item in (planner_code_variants or [])])

    # Keep order but deduplicate.
    seen: set[str] = set()
    deduped: list[str] = []
    entrypoint_intent = has_entrypoint_intent(question)
    for term in terms:
        if term in seen:
            continue
        if term in STOP_WORDS:
            continue
        if term in GENERIC_QUERY_TERMS and not (
            entrypoint_intent and term in {"main", "entry", "point"}
        ):
            continue
        seen.add(term)
        deduped.append(term)

    if entrypoint_intent:
        for hint in ("__main__", "main(", "argparse", "entrypoint"):
            if hint in seen:
                continue
            seen.add(hint)
            deduped.append(hint)

    lowered_question = normalize_question(question).lower()
    if "llm" in lowered_question and any(marker in lowered_question for marker in ("aufruf", "call", "request")):
        for hint in ("openai", "chat.completions", "responses.create", "litellm", "openai_compatible_complete"):
            if hint in seen:
                continue
            seen.add(hint)
            deduped.append(hint)

    if profile == Profile.SIMPLE:
        return deduped[:5]
    if profile == Profile.STANDARD:
        return deduped[:10]
    return deduped[:15]


def derive_exact_fallback_terms(question: str, profile: Profile) -> list[str]:
    normalized = normalize_question(question)
    if not normalized:
        return []
    quoted_phrases = re.findall(r'"([^"]+)"', question)
    raw_tokens = re.findall(r"\S+", question)
    terms: list[str] = [normalized.lower()]
    terms.extend(phrase.strip().lower() for phrase in quoted_phrases if phrase.strip())
    for token in raw_tokens:
        cleaned = token.strip().strip(".,;:!?()[]{}\"'").lower()
        if not cleaned:
            continue
        terms.append(cleaned)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    if profile == Profile.SIMPLE:
        return deduped[:5]
    if profile == Profile.STANDARD:
        return deduped[:10]
    return deduped[:15]


def has_entrypoint_intent(question: str) -> bool:
    lowered = normalize_question(question).lower()
    if any(phrase in lowered for phrase in ENTRYPOINT_PHRASES):
        return True
    return "main" in lowered and "entry" in lowered


def has_write_request_intent(question: str) -> bool:
    lowered = question.lower()
    if any(token in lowered for token in ("write ", "modify ", "create ", "apply patch", "git add", "commit ")):
        return True
    tokens = re.findall(r"[A-Za-z0-9_./-]+", lowered)
    for token in tokens:
        if any(hint in token for hint in WRITE_REQUEST_HINTS):
            return True
    return False


def collect_matches(
    root: Path,
    terms: list[str],
    session: ExecutionSession,
) -> dict[str, list[Evidence]]:
    results: dict[str, list[Evidence]] = {}
    if not terms:
        return results

    for file_path in iter_repo_files(root, session):
        rel = str(file_path.relative_to(root))

        content = read_text_file(file_path, session)
        if not content:
            continue

        lines = content.splitlines()
        evidences: list[Evidence] = []
        for idx, line in enumerate(lines, start=1):
            haystack = line.lower()
            matched_term = next((term for term in terms if term in haystack), None)
            if matched_term is None:
                continue
            evidences.append(Evidence(line=idx, text=line.strip(), term=matched_term))
            if len(evidences) >= 12:
                break

        if evidences:
            results[rel] = evidences
    return results


def score_candidate(
    candidate_path: Path,
    evidences: list[Evidence],
    path_class: str,
    *,
    entrypoint_intent: bool,
    llm_call_intent: bool,
    target_scope: str | None,
    entity_types: list[str],
    index_explain_summary: str | None,
    question_terms: set[str],
) -> int:
    unique_terms = {e.term for e in evidences}
    base = len(evidences) + (len(unique_terms) * 2)
    class_bonus = path_class_weight(path_class)
    score = base + class_bonus

    if entrypoint_intent:
        rel = str(candidate_path).lower()
        if rel in ENTRYPOINT_PATH_HINTS:
            score += 9
        elif rel.endswith("/__main__.py") or rel.endswith("/main.py"):
            score += 7
        line_boost = 0
        for evidence in evidences[:8]:
            line_lower = evidence.text.lower()
            if any(hint in line_lower for hint in ENTRYPOINT_LINE_HINTS):
                line_boost += 2
        score += min(line_boost, 8)

    if llm_call_intent:
        rel = str(candidate_path).lower()
        if rel == "core/llm_integration.py" or rel.endswith("/llm_integration.py"):
            score += 14
        elif rel.startswith("core/"):
            score += 4
        elif rel.startswith("docs/"):
            score -= 6
        line_boost = 0
        for evidence in evidences[:10]:
            line_lower = evidence.text.lower()
            if any(hint in line_lower for hint in LLM_CALL_LINE_HINTS):
                line_boost += 3
        score += min(line_boost, 12)

    rel = str(candidate_path).lower()
    if target_scope == "code":
        if rel.startswith("docs/") or rel.endswith(".md"):
            score -= 8
        else:
            score += 3
    elif target_scope == "docs":
        if rel.startswith("docs/") or rel.endswith(".md"):
            score += 6
        else:
            score -= 3

    if "api_call" in entity_types:
        for evidence in evidences[:10]:
            line_lower = evidence.text.lower()
            if "(" in line_lower and any(marker in line_lower for marker in ("openai", "request", "chat", "responses")):
                score += 2
                break

    if index_explain_summary:
        lowered = index_explain_summary.lower()
        overlap = sum(1 for term in question_terms if term in lowered)
        score += min(overlap, 4)

    return score


def rank_candidates(
    matches: dict[str, list[Evidence]],
    *,
    path_classes: dict[str, str],
    entrypoint_intent: bool,
    llm_call_intent: bool,
    target_scope: str | None,
    entity_types: list[str],
    index_entry_map: dict[str, dict[str, object]],
    question_terms: set[str],
) -> list[Candidate]:
    ranked: list[Candidate] = []
    for rel_path, evidences in matches.items():
        path_class = path_classes.get(rel_path, "normal")
        ranked.append(
            Candidate(
                path=Path(rel_path),
                evidences=evidences,
                score=score_candidate(
                    Path(rel_path),
                    evidences,
                    path_class,
                    entrypoint_intent=entrypoint_intent,
                    llm_call_intent=llm_call_intent,
                    target_scope=target_scope,
                    entity_types=entity_types,
                    index_explain_summary=(
                        str(index_entry_map.get(rel_path, {}).get("explain_summary"))
                        if isinstance(index_entry_map.get(rel_path, {}).get("explain_summary"), str)
                        else None
                    ),
                    question_terms=question_terms,
                ),
                path_class=path_class,
            )
        )
    ranked.sort(key=lambda c: (c.score, len(c.evidences)), reverse=True)
    return ranked


def _question_terms_for_intent(question: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9_./-]+", question.lower())
    terms: set[str] = set()
    for token in tokens:
        for part in [token, *[p for p in re.split(r"[-_/]", token) if p]]:
            if len(part) < 3:
                continue
            if part in STOP_WORDS or part in STOP_WORDS_DE:
                continue
            terms.add(part)
    return terms


def build_explain_feedback(
    *,
    question: str,
    candidates: list[Candidate],
) -> list[ExplainFeedback]:
    question_terms = _question_terms_for_intent(question)
    feedback: list[ExplainFeedback] = []
    for candidate in candidates:
        rel = str(candidate.path).lower()
        path_tokens = set(re.findall(r"[A-Za-z0-9_./-]+", rel))
        evidence_terms = {e.term.lower() for e in candidate.evidences}
        intent_overlap = len(question_terms.intersection(path_tokens | evidence_terms))
        intent_match = intent_overlap > 0
        evidence_density = min(1.0, len(candidate.evidences) / 8.0)
        rationale: list[str] = []
        if intent_match:
            rationale.append(f"intent term overlap={intent_overlap}")
        else:
            rationale.append("no direct intent-term overlap")
        rationale.append(f"evidence density={evidence_density:.2f}")

        score = candidate.score
        if intent_match:
            score += 4 + min(intent_overlap, 3)
        if evidence_density >= 0.75:
            score += 4
        elif evidence_density >= 0.4:
            score += 2
        if rel.startswith("docs/") and any(term in question_terms for term in {"function", "class", "api", "llm"}):
            score -= 3
            rationale.append("docs penalty for code-oriented intent")

        if evidence_density >= 0.75 and intent_match:
            linkage_confidence = "high"
        elif evidence_density >= 0.4 or intent_match:
            linkage_confidence = "medium"
        else:
            linkage_confidence = "low"

        feedback.append(
            ExplainFeedback(
                path=candidate.path,
                intent_match=intent_match,
                evidence_density=round(evidence_density, 3),
                linkage_confidence=linkage_confidence,
                relevance_score=score,
                rationale=rationale,
            )
        )
    return feedback


def rerank_with_explain_feedback(candidates: list[Candidate], feedback: list[ExplainFeedback]) -> list[Candidate]:
    score_by_path = {str(item.path): item.relevance_score for item in feedback}
    reranked = list(candidates)
    reranked.sort(
        key=lambda c: (
            score_by_path.get(str(c.path), c.score),
            len(c.evidences),
            c.score,
        ),
        reverse=True,
    )
    return reranked


def format_summary(question: str, candidates: list[Candidate]) -> str:
    if not candidates:
        return f"No strong locations found for: {question}"
    top_paths = ", ".join(str(candidate.path) for candidate in candidates[:3])
    return f"Most likely relevant files: {top_paths}."


def human_summary(summary: str, view: str) -> str:
    if is_full(view):
        return summary
    cleaned_lines: list[str] = []
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("deterministic summary"):
            continue
        if lowered.startswith("evidence:"):
            break
        cleaned_lines.append(line)
        if len(cleaned_lines) >= 2:
            break
    return " ".join(cleaned_lines) if cleaned_lines else summary


def print_output(
    question: str,
    candidates: list[Candidate],
    summary: str,
    view: str,
    cross_lingual: CrossLingualExpansion,
    interpreted_question: str | None,
) -> None:
    print("\n--- Answer ---")
    print(human_summary(summary, view))
    if interpreted_question and is_full(view):
        print(f"Interpreted question: {interpreted_question}")
    if cross_lingual.mapped_terms and is_full(view):
        mapped = ", ".join(
            f"{item['source_term']}->{item['mapped_term']}" for item in cross_lingual.mapped_terms[:4]
        )
        print(f"Cross-lingual mapping ({cross_lingual.source_language}): {mapped}")

    if not candidates:
        if not is_compact(view):
            print("\n--- Likely Locations ---")
            print("No likely locations found.")
            if is_full(view):
                print("\n--- Evidence ---")
                print("No evidence found.")
        print("\n--- Next Step ---")
        print("Try a narrower question with a concrete symbol or path fragment.")
        return

    print("\n--- Top Files ---")
    location_limit = 1 if is_compact(view) else 3 if view == "standard" else 8
    for idx, candidate in enumerate(candidates[:location_limit], start=1):
        if is_full(view):
            print(
                f"{idx}. {candidate.path} "
                f"(score={candidate.score}, class={candidate.path_class}, matches={len(candidate.evidences)})"
            )
        else:
            print(f"{idx}. {candidate.path} ({len(candidate.evidences)} matches)")

    if not is_compact(view):
        print("\n--- Why ---")
        evidence_candidate_limit = 2 if view == "standard" else 5
        evidence_line_limit = 2 if view == "standard" else 3
        for candidate in candidates[:evidence_candidate_limit]:
            for evidence in candidate.evidences[:evidence_line_limit]:
                print(f"{candidate.path}:{evidence.line}: {evidence.text} [term={evidence.term}]")

    print("\n--- Next Step ---")
    print(f"Run: forge explain {candidates[0].path}")


def enrich_detailed_context(
    root: Path,
    candidates: list[Candidate],
    session: ExecutionSession,
) -> list[str]:
    details: list[str] = []
    for candidate in candidates[:3]:
        abs_path = root / candidate.path
        content = read_text_file(abs_path, session)
        if not content:
            continue
        lines = content.splitlines()
        focus_lines = [e.line for e in candidate.evidences[:2]]
        for focus in focus_lines:
            start = max(1, focus - 1)
            end = min(len(lines), focus + 1)
            for lineno in range(start, end + 1):
                details.append(f"{candidate.path}:{lineno}: {lines[lineno - 1].strip()}")
    return details


def deterministic_interpreted_question(question: str, cross_lingual: CrossLingualExpansion) -> str | None:
    if cross_lingual.source_language != "de" or not cross_lingual.mapped_terms:
        return None
    mapped_by_source = {item["source_term"]: item["mapped_term"] for item in cross_lingual.mapped_terms}
    tokens = re.findall(r"[A-Za-z0-9_./-]+", normalize_question(question).lower())
    translated_tokens: list[str] = []
    for token in tokens:
        translated_tokens.append(mapped_by_source.get(token, token))
    if not translated_tokens:
        return None
    interpreted = " ".join(translated_tokens[:16]).strip()
    return interpreted if interpreted and interpreted != normalize_question(question).lower() else None

def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    is_json = args.output_format == "json"
    view = resolve_view(args)
    if not is_json:
        print("=== FORGE QUERY ===")
        print(f"Profile: {request.profile.value}")
        print(f"Question: {request.payload}")

    repo_root = Path(args.repo_root).resolve()
    question = normalize_question(request.payload)
    policy_violations: list[dict[str, object]] = []
    if has_write_request_intent(question):
        violation = evaluate_action_eligibility(
            capability=request.capability,
            action="repo_write",
            phase="planner",
            detail="query mode is read-only; write-like user intent was blocked",
        )
        if violation is not None:
            policy_violations.append(violation.to_dict())
    llm_settings = resolve_settings(args, repo_root)
    query_input_mode = getattr(args, "query_input_mode", "planner")
    cross_lingual = build_cross_lingual_expansion(question, request.profile)
    planner = None
    if query_input_mode == "planner":
        baseline_terms = []
        planner = maybe_plan_query_terms(
            capability=request.capability,
            profile=request.profile,
            question=question,
            source_language=cross_lingual.source_language,
            deterministic_terms=baseline_terms,
            settings=llm_settings,
            repo_root=repo_root,
        )

    if planner is not None and planner.usage.get("used"):
        terms: list[str] = []
        terms.extend([item.lower() for item in planner.search_terms])
        terms.extend([item.lower() for item in planner.code_variants])
        deduped_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in terms:
            normalized_term = " ".join(term.strip().split())
            if not normalized_term:
                continue
            if normalized_term in seen_terms:
                continue
            seen_terms.add(normalized_term)
            deduped_terms.append(normalized_term)
        terms = deduped_terms[:20]
    else:
        # Fallback is strict: only use exactly requested query terms.
        terms = derive_exact_fallback_terms(question, request.profile)
        cross_lingual = CrossLingualExpansion(
            source_language="unknown",
            mapped_terms=[],
            expansion_mode="disabled_exact_mode" if query_input_mode == "exact" else "disabled_fallback",
        )

    path_classes: dict[str, str] = {}
    index_entry_map: dict[str, dict[str, object]] = {}
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        path_classes = load_index_path_class_map(repo_root, session)
        index_entry_map = load_index_entry_map(repo_root, session)
        if not is_json:
            if path_classes:
                print("Index: loaded .forge/index.json")
            else:
                print("Index: not available, using direct repository scan only")
    elif not is_json:
        print("Index: skipped in simple profile")

    if not is_json and is_full(view):
        print(f"Search terms: {', '.join(terms[:8])}" if terms else "Search terms: none")
    matches = collect_matches(
        repo_root,
        terms,
        session,
    )
    llm_call_intent = bool(planner is not None and planner.usage.get("used")) and (planner.intent or "").strip().lower() in {
        "llm_usage_locations",
        "llm_calls",
    }
    candidates = rank_candidates(
        matches,
        path_classes=path_classes,
        entrypoint_intent=has_entrypoint_intent(question),
        llm_call_intent=llm_call_intent,
        target_scope=planner.target_scope if planner is not None else None,
        entity_types=planner.entity_types if planner is not None else [],
        index_entry_map=index_entry_map,
        question_terms=_question_terms_for_intent(question),
    )
    explain_feedback = build_explain_feedback(question=question, candidates=candidates[:12])
    candidates = rerank_with_explain_feedback(candidates, explain_feedback)
    feedback_by_path = {str(item.path): item for item in explain_feedback}
    top_feedback = feedback_by_path.get(str(candidates[0].path)) if candidates else None
    detailed_lines: list[str] = []
    if request.profile == Profile.DETAILED and candidates:
        detailed_lines = enrich_detailed_context(repo_root, candidates, session)

    evidence_payload: list[dict[str, object]] = []
    for candidate in candidates[:5]:
        for item in candidate.evidences[:3]:
            evidence_payload.append(
                {
                    "path": str(candidate.path),
                    "line": item.line,
                    "text": item.text,
                    "term": item.term,
                }
            )
    orchestration = maybe_orchestrate_query_actions(
        capability=request.capability,
        profile=request.profile,
        question=question,
        candidate_paths=[str(item.path) for item in candidates[:12]],
        evidence_count=len(evidence_payload),
        settings=llm_settings,
        repo_root=repo_root,
    )
    adaptive_continue = bool(top_feedback is not None and top_feedback.linkage_confidence == "low" and len(candidates) > 1)
    if orchestration.decisions:
        first_decision = orchestration.decisions[0]
        if (
            (first_decision.decision == "continue" and first_decision.next_action == "read")
            or adaptive_continue
        ) and candidates:
            start_idx = 1 if adaptive_continue else 0
            inspect_slice = candidates[start_idx : start_idx + max(1, min(len(candidates), llm_settings.query_orchestrator_max_files))]
            bounded_details = enrich_detailed_context(
                repo_root,
                inspect_slice,
                session,
            )
            extra_limit = min(len(bounded_details), llm_settings.query_orchestrator_max_tokens // 40)
            for raw in bounded_details[:extra_limit]:
                if raw.count(":") < 2:
                    continue
                path_part, line_part, text_part = raw.split(":", 2)
                try:
                    line_no = int(line_part)
                except ValueError:
                    continue
                evidence_payload.append(
                    {
                        "path": path_part.strip(),
                        "line": line_no,
                        "text": text_part.strip(),
                        "term": "orchestrator_read",
                    }
                )
            if bounded_details:
                detailed_lines.extend(bounded_details[:12])

    summary = format_summary(question, candidates)
    uncertainty = ["Results are based on lexical matching and heuristic ranking."]
    if request.profile == Profile.SIMPLE:
        uncertainty.append("Simple profile does not use index-assisted prioritization.")
    if planner is None:
        uncertainty.append("Exact input mode active: no translation/replacement/expansion was applied.")
    elif not planner.usage.get("used"):
        reason = str(planner.usage.get("fallback_reason") or "unknown planner fallback")
        uncertainty.append(
            f"Planner unavailable; using exact user terms only (no translation/replacement/expansion): {reason}"
        )
    if not candidates:
        uncertainty.append("No strong candidate files were detected.")
    if top_feedback and top_feedback.linkage_confidence == "low":
        uncertainty.append("Top match confidence is low; query performed bounded additional inspection.")
    if policy_violations:
        uncertainty.append(
            "Mode boundary enforced: query is read-only; write request was blocked and analysis continued read-only."
        )
    if orchestration.done_reason == "budget_exhausted":
        uncertainty.append("Query action orchestration hit configured budget limits.")
    if orchestration.done_reason == "policy_blocked":
        uncertainty.append("Query action orchestration decision was rejected; deterministic fallback was used.")
    next_step = (
        f"Run: forge explain {candidates[0].path}"
        if candidates
        else "Try a narrower question with a concrete symbol or path fragment."
    )
    llm_outcome = maybe_refine_summary(
        capability=request.capability,
        profile=request.profile,
        task=question,
        deterministic_summary=summary,
        evidence=evidence_payload,
        settings=llm_settings,
        repo_root=repo_root,
    )
    summary = llm_outcome.summary
    uncertainty.extend(llm_outcome.uncertainty_notes)

    sections: dict[str, object] = {
        "likely_locations": [
            {
                "path": str(candidate.path),
                "score": candidate.score,
                "path_class": candidate.path_class,
                "matches": len(candidate.evidences),
            }
            for candidate in candidates[:8]
        ],
        "explain_feedback": [
            {
                "path": str(item.path),
                "intent_match": item.intent_match,
                "evidence_density": item.evidence_density,
                "linkage_confidence": item.linkage_confidence,
                "relevance_score": item.relevance_score,
                "rationale": item.rationale,
            }
            for item in explain_feedback[:8]
        ],
        "index_explain_summaries": [
            {
                "path": str(candidate.path),
                "explain_summary": (
                    index_entry_map.get(str(candidate.path), {}).get("explain_summary")
                    if isinstance(index_entry_map.get(str(candidate.path), {}).get("explain_summary"), str)
                    else None
                ),
                "summary_version": (
                    index_entry_map.get(str(candidate.path), {}).get("summary_version")
                    if isinstance(index_entry_map.get(str(candidate.path), {}).get("summary_version"), int)
                    else None
                ),
            }
            for candidate in candidates[:5]
            if str(candidate.path) in index_entry_map
        ],
        "llm_usage": llm_outcome.usage,
        "provenance": provenance_section(
            llm_used=bool(llm_outcome.usage.get("used")),
            evidence_count=len(evidence_payload),
        ),
        "cross_lingual": {
            "source_language": cross_lingual.source_language,
            "mapped_terms": cross_lingual.mapped_terms,
            "expansion_mode": cross_lingual.expansion_mode,
        },
        "query_planner": {
            "normalized_question_en": planner.normalized_question_en if planner is not None else None,
            "intent": planner.intent if planner is not None else None,
            "target_scope": planner.target_scope if planner is not None else None,
            "entity_types": planner.entity_types if planner is not None else [],
            "search_terms": planner.search_terms if planner is not None else [],
            "code_variants": planner.code_variants if planner is not None else [],
            "dropped_filler_terms": planner.dropped_filler_terms if planner is not None else [],
            "usage": (
                planner.usage
                if planner is not None
                else {
                    "enabled": False,
                    "mode": "off",
                    "attempted": False,
                    "used": False,
                    "provider": llm_settings.provider,
                    "model": llm_settings.model,
                    "output_language": llm_settings.output_language,
                    "prompt_template": "prompts/llm/query_planner.txt",
                    "fallback_reason": "skipped by --query-input-mode exact",
                    "latency_ms": None,
                    "source_language": "unknown",
                }
            ),
        },
        "policy_violations": policy_violations,
        "action_orchestration": {
            "catalog": ["search", "read", "explain", "rank", "summarize", "stop"],
            "budgets": {
                "max_iterations": llm_settings.query_orchestrator_max_iterations,
                "max_files": llm_settings.query_orchestrator_max_files,
                "max_tokens": llm_settings.query_orchestrator_max_tokens,
                "max_wall_time_ms": llm_settings.query_orchestrator_max_wall_time_ms,
            },
            "decisions": [
                {
                    "decision": d.decision,
                    "next_action": d.next_action,
                    "reason": d.reason,
                    "confidence": d.confidence,
                }
                for d in orchestration.decisions
            ],
            "done_reason": orchestration.done_reason,
            "usage": orchestration.usage,
            "adaptive_continuation_triggered": adaptive_continue,
        },
    }
    if detailed_lines:
        sections["detailed_context"] = detailed_lines[:20]

    contract = build_contract(
        capability=request.capability.value,
        profile=request.profile.value,
        summary=summary,
        evidence=evidence_payload,
        uncertainty=uncertainty,
        next_step=next_step,
        sections=sections,
    )
    if is_json:
        emit_contract_json(contract)
        return 0

    print_output(
        question,
        candidates,
        summary,
        view,
        cross_lingual,
        planner.normalized_question_en if planner is not None else None,
    )
    if policy_violations:
        print("\n--- Mode Boundary ---")
        for item in policy_violations:
            print(
                f"Blocked action '{item.get('blocked_action')}' "
                f"for capability '{item.get('capability')}' at phase '{item.get('phase')}'."
            )
            detail = item.get("detail")
            if isinstance(detail, str) and detail:
                print(f"Reason: {detail}")
    if is_full(view):
        print("\n--- Index Summary Hints ---")
        for candidate in candidates[:5]:
            entry = index_entry_map.get(str(candidate.path), {})
            explain_summary = entry.get("explain_summary")
            if isinstance(explain_summary, str) and explain_summary.strip():
                version = entry.get("summary_version")
                print(f"{candidate.path} (v{version if isinstance(version, int) else '-'})")
                print(f"  {explain_summary[:180]}")

        print("\n--- Explain Feedback ---")
        for item in explain_feedback[:5]:
            print(
                f"{item.path}: confidence={item.linkage_confidence} "
                f"intent_match={item.intent_match} density={item.evidence_density:.2f} score={item.relevance_score}"
            )
            print(f"  why: {', '.join(item.rationale[:2])}")

        print("\n--- Query Planner ---")
        planner_usage = (
            planner.usage
            if planner is not None
            else {
                "used": False,
                "mode": "off",
                "provider": llm_settings.provider,
                "model": llm_settings.model,
                "output_language": llm_settings.output_language,
                "fallback_reason": "skipped by --query-input-mode exact",
            }
        )
        print(f"Used: {planner_usage.get('used')}")
        print(f"Mode: {planner_usage.get('mode')}")
        print(f"Provider: {planner_usage.get('provider') or 'none'}")
        print(f"Model: {planner_usage.get('model') or 'none'}")
        if planner is not None and planner.normalized_question_en:
            print(f"Normalized question: {planner.normalized_question_en}")
        if planner is not None and planner.intent:
            print(f"Intent: {planner.intent}")
        if planner is not None and planner.target_scope:
            print(f"Target scope: {planner.target_scope}")
        if planner is not None and planner.entity_types:
            print(f"Entity types: {', '.join(planner.entity_types)}")
        if planner is not None and planner.search_terms:
            print(f"Planner terms: {', '.join(planner.search_terms[:8])}")
        if planner is not None and planner.code_variants:
            print(f"Code variants: {', '.join(planner.code_variants[:8])}")
        if planner_usage.get("fallback_reason"):
            print(f"Fallback: {planner_usage['fallback_reason']}")

        print("\n--- Action Orchestration ---")
        print(f"Done reason: {orchestration.done_reason}")
        if orchestration.decisions:
            for idx, decision in enumerate(orchestration.decisions, start=1):
                print(
                    f"{idx}. decision={decision.decision} "
                    f"next_action={decision.next_action or '-'} "
                    f"confidence={decision.confidence}"
                )
                print(f"   reason: {decision.reason}")
        if orchestration.usage.get("fallback_reason"):
            print(f"Fallback: {orchestration.usage['fallback_reason']}")

        print("\n--- LLM Usage ---")
        print(f"Policy: {llm_outcome.usage['policy']}")
        print(f"Mode: {llm_outcome.usage['mode']}")
        print(f"Used: {llm_outcome.usage['used']}")
        print(f"Provider: {llm_outcome.usage['provider'] or 'none'}")
        print(f"Base URL: {llm_outcome.usage['base_url'] or 'none'}")
        print(f"Model: {llm_outcome.usage['model'] or 'none'}")
        print(f"Output language: {llm_outcome.usage.get('output_language') or 'auto'}")
        if llm_outcome.usage.get("fallback_reason"):
            print(f"Fallback: {llm_outcome.usage['fallback_reason']}")
        print("\n--- Provenance ---")
        print(f"Evidence items: {len(evidence_payload)}")
        print(
            "Inference source: "
            + ("deterministic heuristics + LLM" if llm_outcome.usage["used"] else "deterministic heuristics")
        )
    print("\n--- Uncertainty ---")
    notes = uncertainty if is_full(view) else uncertainty[:1]
    for note in notes:
        print(f"- {note}")

    if detailed_lines and is_full(view):
            print("\n--- Detailed Context ---")
            for line in detailed_lines[:20]:
                print(line)
    return 0
