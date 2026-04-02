from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core.capability_model import CommandRequest, EffectClass, Profile
from core.effects import ExecutionSession
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


def normalize_question(question: str) -> str:
    return " ".join(question.strip().split())


def derive_search_terms(question: str, profile: Profile) -> list[str]:
    quoted_phrases = re.findall(r'"([^"]+)"', question)
    word_tokens = re.findall(r"[A-Za-z0-9_./-]+", question.lower())
    filtered_words = [w for w in word_tokens if len(w) >= 3 and w not in STOP_WORDS]

    terms: list[str] = []
    normalized_question = normalize_question(question)
    if normalized_question:
        terms.append(normalized_question.lower())
    terms.extend([phrase.strip().lower() for phrase in quoted_phrases if phrase.strip()])
    terms.extend(filtered_words)

    # Keep order but deduplicate.
    seen: set[str] = set()
    deduped: list[str] = []
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


def load_index_path_classes(repo_root: Path, session: ExecutionSession) -> dict[str, str]:
    index_file = repo_root / ".forge" / "index.json"
    if not index_file.exists():
        return {}

    session.record_effect(EffectClass.READ_ONLY, f"read index metadata {index_file}")
    try:
        raw = index_file.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}

    entries = payload.get("entries", {})
    files = entries.get("files", [])
    if not isinstance(files, list):
        return {}

    mapping: dict[str, str] = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        path_class = entry.get("path_class", "normal")
        if isinstance(path, str) and isinstance(path_class, str):
            mapping[path] = path_class
    return mapping


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


def score_candidate(evidences: list[Evidence], path_class: str) -> int:
    unique_terms = {e.term for e in evidences}
    base = len(evidences) + (len(unique_terms) * 2)
    class_bonus = {
        "preferred": 3,
        "normal": 0,
        "low_priority": -1,
        "index_exclude": -3,
        "hard_ignore": -5,
    }.get(path_class, 0)
    return base + class_bonus


def rank_candidates(
    matches: dict[str, list[Evidence]],
    *,
    path_classes: dict[str, str],
) -> list[Candidate]:
    ranked: list[Candidate] = []
    for rel_path, evidences in matches.items():
        path_class = path_classes.get(rel_path, "normal")
        ranked.append(
            Candidate(
                path=Path(rel_path),
                evidences=evidences,
                score=score_candidate(evidences, path_class),
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
        f"Most likely entry point is '{top.path}' based on {len(top.evidences)} "
        f"direct match(es)."
    )


def print_output(question: str, candidates: list[Candidate]) -> None:
    print("\n--- Summary ---")
    print(format_summary(question, candidates))

    if not candidates:
        print("\n--- Likely Locations ---")
        print("No likely locations found.")
        print("\n--- Evidence ---")
        print("No evidence found.")
        print("\n--- Next Step ---")
        print("Try a narrower question with a concrete symbol or path fragment.")
        return

    print("\n--- Likely Locations ---")
    for idx, candidate in enumerate(candidates[:8], start=1):
        print(
            f"{idx}. {candidate.path} "
            f"(score={candidate.score}, class={candidate.path_class}, matches={len(candidate.evidences)})"
        )

    print("\n--- Evidence ---")
    for candidate in candidates[:5]:
        for evidence in candidate.evidences[:3]:
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
    print("=== FORGE QUERY ===")
    print(f"Profile: {request.profile.value}")
    print(f"Question: {request.payload}")

    repo_root = Path(args.repo_root).resolve()
    question = normalize_question(request.payload)
    terms = derive_search_terms(question, request.profile)

    path_classes: dict[str, str] = {}
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        path_classes = load_index_path_classes(repo_root, session)
        if path_classes:
            print("Index: loaded .forge/index.json")
        else:
            print("Index: not available, using direct repository scan only")
    else:
        print("Index: skipped in simple profile")

    print(f"Search terms: {', '.join(terms[:8])}" if terms else "Search terms: none")
    matches = collect_matches(
        repo_root,
        terms,
        session,
    )
    candidates = rank_candidates(matches, path_classes=path_classes)

    print_output(question, candidates)

    if request.profile == Profile.DETAILED and candidates:
        detailed = enrich_detailed_context(repo_root, candidates, session)
        if detailed:
            print("\n--- Detailed Context ---")
            for line in detailed[:20]:
                print(line)
    return 0
