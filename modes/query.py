from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import load_index_path_class_map, path_class_weight
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import maybe_refine_summary, provenance_section, resolve_settings
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
    "funktion",
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


def normalize_question(question: str) -> str:
    return " ".join(question.strip().split())


def detect_language(question: str) -> str:
    lowered = normalize_question(question).lower()
    if re.search(r"[äöüß]", lowered):
        return "de"
    tokens = re.findall(r"[A-Za-z0-9_./-]+", lowered)
    if not tokens:
        return "unknown"
    de_hits = sum(1 for token in tokens if token in LANGUAGE_HINTS_DE)
    if de_hits >= 2:
        return "de"
    return "en"


def build_cross_lingual_expansion(question: str, profile: Profile) -> CrossLingualExpansion:
    source_language = detect_language(question)
    tokens = re.findall(r"[A-Za-z0-9_./-]+", normalize_question(question).lower())
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
) -> list[str]:
    quoted_phrases = re.findall(r'"([^"]+)"', question)
    word_tokens = re.findall(r"[A-Za-z0-9_./-]+", question.lower())
    filtered_words = [w for w in word_tokens if len(w) >= 3 and w not in STOP_WORDS]

    terms: list[str] = []
    normalized_question = normalize_question(question)
    if normalized_question:
        terms.append(normalized_question.lower())
    terms.extend([phrase.strip().lower() for phrase in quoted_phrases if phrase.strip()])
    terms.extend(filtered_words)
    terms.extend(item["mapped_term"] for item in cross_lingual.mapped_terms)

    # Keep order but deduplicate.
    seen: set[str] = set()
    deduped: list[str] = []
    entrypoint_intent = has_entrypoint_intent(question)
    for term in terms:
        if term in seen:
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

    return score


def rank_candidates(
    matches: dict[str, list[Evidence]],
    *,
    path_classes: dict[str, str],
    entrypoint_intent: bool,
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
                ),
                path_class=path_class,
            )
        )
    ranked.sort(key=lambda c: (c.score, len(c.evidences)), reverse=True)
    return ranked


def format_summary(question: str, candidates: list[Candidate]) -> str:
    if not candidates:
        return f"No strong locations found for: {question}"
    top = candidates[0]
    return (
        f"Most likely relevant location is '{top.path}' based on {len(top.evidences)} "
        f"direct match(es)."
    )


def print_output(
    question: str,
    candidates: list[Candidate],
    summary: str,
    view: str,
    cross_lingual: CrossLingualExpansion,
) -> None:
    print("\n--- Summary ---")
    print(summary)
    if cross_lingual.mapped_terms and not is_compact(view):
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

    print("\n--- Likely Locations ---")
    location_limit = 1 if is_compact(view) else 3 if view == "standard" else 8
    for idx, candidate in enumerate(candidates[:location_limit], start=1):
        print(
            f"{idx}. {candidate.path} "
            f"(score={candidate.score}, class={candidate.path_class}, matches={len(candidate.evidences)})"
        )

    if not is_compact(view):
        print("\n--- Evidence ---")
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

def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    is_json = args.output_format == "json"
    view = resolve_view(args)
    if not is_json:
        print("=== FORGE QUERY ===")
        print(f"Profile: {request.profile.value}")
        print(f"Question: {request.payload}")

    repo_root = Path(args.repo_root).resolve()
    question = normalize_question(request.payload)
    cross_lingual = build_cross_lingual_expansion(question, request.profile)
    terms = derive_search_terms(question, request.profile, cross_lingual)

    path_classes: dict[str, str] = {}
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        path_classes = load_index_path_class_map(repo_root, session)
        if not is_json:
            if path_classes:
                print("Index: loaded .forge/index.json")
            else:
                print("Index: not available, using direct repository scan only")
    elif not is_json:
        print("Index: skipped in simple profile")

    if not is_json:
        print(f"Search terms: {', '.join(terms[:8])}" if terms else "Search terms: none")
    matches = collect_matches(
        repo_root,
        terms,
        session,
    )
    candidates = rank_candidates(
        matches,
        path_classes=path_classes,
        entrypoint_intent=has_entrypoint_intent(question),
    )
    detailed_lines: list[str] = []
    if request.profile == Profile.DETAILED and candidates:
        detailed_lines = enrich_detailed_context(repo_root, candidates, session)

    summary = format_summary(question, candidates)
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
    uncertainty = ["Results are based on lexical matching and heuristic ranking."]
    if request.profile == Profile.SIMPLE:
        uncertainty.append("Simple profile does not use index-assisted prioritization.")
    if cross_lingual.source_language == "unknown":
        uncertainty.append("Source language could not be determined confidently for cross-lingual expansion.")
    if not candidates:
        uncertainty.append("No strong candidate files were detected.")
    next_step = (
        f"Run: forge explain {candidates[0].path}"
        if candidates
        else "Try a narrower question with a concrete symbol or path fragment."
    )
    llm_settings = resolve_settings(args, repo_root)
    llm_outcome = maybe_refine_summary(
        capability=request.capability,
        profile=request.profile,
        task=question,
        deterministic_summary=summary,
        evidence=evidence_payload,
        settings=llm_settings,
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
    }
    if detailed_lines:
        sections["detailed_context"] = detailed_lines[:20]

    if is_json:
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=evidence_payload,
            uncertainty=uncertainty,
            next_step=next_step,
            sections=sections,
        )
        emit_contract_json(contract)
        return 0

    print_output(question, candidates, summary, view, cross_lingual)
    if is_full(view):
        print("\n--- LLM Usage ---")
        print(f"Policy: {llm_outcome.usage['policy']}")
        print(f"Mode: {llm_outcome.usage['mode']}")
        print(f"Used: {llm_outcome.usage['used']}")
        print(f"Provider: {llm_outcome.usage['provider'] or 'none'}")
        print(f"Base URL: {llm_outcome.usage['base_url'] or 'none'}")
        print(f"Model: {llm_outcome.usage['model'] or 'none'}")
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

    if detailed_lines:
            print("\n--- Detailed Context ---")
            for line in detailed_lines[:20]:
                print(line)
    return 0
