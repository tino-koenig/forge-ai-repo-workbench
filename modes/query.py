from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
import time

from core.analysis_primitives import load_index_entry_map, load_index_path_class_map, path_class_weight
from core.capability_model import CommandRequest, EffectClass, Profile
from core.effects import ExecutionSession
from core.framework_profiles import FrameworkProfile, load_framework_registry, select_framework_profile
from core.graph_cache import load_framework_graph_references, load_repo_graph
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
from core.repo_io import TEXT_FILE_EXTENSIONS, iter_repo_files, read_text_file


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
    "show",
    "where",
    "which",
}

WEAK_GENERIC_TERMS = {
    "where",
    "what",
    "which",
    "find",
    "show",
    "code",
    "source",
    "location",
    "file",
    "files",
}

SQL_WHERE_CONTEXT_HINTS = {
    "sql",
    "select",
    "from",
    "where",
    "join",
    "group",
    "order",
    "having",
    "query builder",
    "querybuilder",
    "criteria",
}

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
    source: str = "content_match"  # content_match | path_match | symbol_match | summary_match | graph_match
    weight: int = 1


@dataclass
class Candidate:
    path: Path
    evidences: list[Evidence]
    score: int
    path_class: str
    retrieval_sources: list[str]
    source_type: str
    source_origin: str
    framework_id: str | None
    framework_version: str | None


@dataclass(frozen=True)
class SourceMetadata:
    source_type: str
    source_origin: str
    framework_id: str | None = None
    framework_version: str | None = None


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


@dataclass
class QueryOrchestrationIteration:
    iteration: int
    decision: str
    next_action: str | None
    reason: str
    confidence: str
    done_reason: str
    evidence_count_before: int
    evidence_count_after: int
    candidate_count_before: int
    candidate_count_after: int
    budget_tokens_before: int
    budget_tokens_after: int
    budget_files_before: int
    budget_files_after: int
    budget_tokens_used: int
    budget_files_used: int
    elapsed_ms: int
    handler_status: str
    handler_detail: str
    top_candidates_before: list[str]
    top_candidates_after: list[str]
    source_distribution_before: dict[str, int]
    source_distribution_after: dict[str, int]
    source_scope: str
    source_scope_reason: str
    source_caps: dict[str, int | bool]
    fallback_trigger: str | None
    blocked_reason: str | None
    progress_score: float
    progress_passed: bool
    progress_components: dict[str, float]


FRAMEWORK_PATH_MARKERS = (
    "vendor/",
    "site-packages/",
    "dist-packages/",
    ".venv/lib/",
)

EXTERNAL_PATH_MARKERS = (
    "third_party/",
    "external/",
    "extern/",
    "deps/",
    "submodules/",
)


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
) -> list[str]:
    planner_driven = bool(planner_terms)
    terms: list[str] = []
    if planner_driven:
        terms.extend([item.lower() for item in (planner_terms or [])])
    else:
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
        normalized_question = normalize_question(question)
        if normalized_question:
            terms.append(normalized_question.lower())
        terms.extend([phrase.strip().lower() for phrase in quoted_phrases if phrase.strip()])
        terms.extend(filtered_words)
        terms.extend(item["mapped_term"] for item in cross_lingual.mapped_terms)

    # Keep order and deduplicate only. Ranking priority is handled by scoring.
    seen: set[str] = set()
    deduped: list[str] = []
    sql_where_context = _is_sql_where_context(question)
    for term in terms:
        normalized_term = " ".join(term.strip().split()).lower()
        if not normalized_term:
            continue
        if normalized_term in seen:
            continue
        if normalized_term in STOP_WORDS or normalized_term in STOP_WORDS_DE:
            continue
        if normalized_term in GENERIC_QUERY_TERMS:
            continue
        if normalized_term in WEAK_GENERIC_TERMS:
            if normalized_term == "where" and not sql_where_context:
                continue
            if normalized_term != "where":
                continue
        seen.add(normalized_term)
        deduped.append(normalized_term)
    if profile == Profile.SIMPLE:
        return deduped[:5]
    if profile == Profile.STANDARD:
        return deduped[:10]
    return deduped[:15]


def compose_planner_terms(
    lead_terms: list[str],
    support_terms: list[str],
    search_terms: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for bucket in (lead_terms, support_terms, search_terms):
        for item in bucket:
            normalized = " ".join(item.strip().split()).lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _is_sql_where_context(question: str) -> bool:
    lowered = normalize_question(question).lower()
    return any(hint in lowered for hint in SQL_WHERE_CONTEXT_HINTS)


def _is_symbol_like_term(term: str) -> bool:
    if not term:
        return False
    if any(ch in term for ch in ("(", ")", "::", ".", "/")):
        return True
    if re.fullmatch(r"[a-z_][a-z0-9_]*", term) and "_" in term and len(term) >= 6:
        return True
    return False


def build_term_weight_map(terms: list[str]) -> dict[str, int]:
    # Weight by search-term position: earlier terms carry more priority.
    weights: dict[str, int] = {}
    for idx, term in enumerate(terms):
        normalized = " ".join(term.strip().split()).lower()
        if not normalized:
            continue
        weight = max(1, 10 - idx)
        existing = weights.get(normalized, 0)
        if weight > existing:
            weights[normalized] = weight
    return weights


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


def has_write_request_intent(question: str) -> bool:
    lowered = question.lower()
    if any(token in lowered for token in ("write ", "modify ", "create ", "apply patch", "git add", "commit ")):
        return True
    tokens = re.findall(r"[A-Za-z0-9_./-]+", lowered)
    for token in tokens:
        if any(hint in token for hint in WRITE_REQUEST_HINTS):
            return True
    return False


def _structural_tokens(raw: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_./-]+", raw.lower())
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(part for part in re.split(r"[\\/._-]+", token) if part)
    out: list[str] = []
    seen: set[str] = set()
    for token in expanded:
        if len(token) < 3:
            continue
        if token in STOP_WORDS or token in STOP_WORDS_DE:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


_IDENT_CHAR_CLASS = r"A-Za-z0-9_"
_WORD_CHAR_CLASS = r"A-Za-z0-9"


def _compile_bounded_term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    # Identifier-like terms should not match inside larger identifiers.
    if re.fullmatch(r"[a-z0-9_]+", term):
        return re.compile(rf"(?<![{_IDENT_CHAR_CLASS}]){escaped}(?![{_IDENT_CHAR_CLASS}])")
    return re.compile(rf"(?<![{_WORD_CHAR_CLASS}]){escaped}(?![{_WORD_CHAR_CLASS}])")


def _line_matches_term(line_lower: str, term: str) -> bool:
    normalized = " ".join(term.strip().split()).lower()
    if not normalized:
        return False
    return bool(_compile_bounded_term_pattern(normalized).search(line_lower))


def _path_term_score(rel_lower: str, term: str) -> tuple[int, list[str]]:
    normalized = " ".join(term.strip().lower().split())
    if not normalized:
        return 0, []

    if _is_symbol_like_term(normalized):
        if normalized in rel_lower:
            return 10, [normalized]
        return 0, []

    rel_parts = [part for part in re.split(r"[\\/._-]+", rel_lower) if part]
    rel_part_set = set(rel_parts)
    matched_tokens: list[str] = []
    score = 0

    if any(marker in normalized for marker in ("/", ".", "_", "-")) and normalized in rel_lower:
        score += 6
        matched_tokens.append(normalized)

    tokens = _structural_tokens(normalized)
    strong = [token for token in tokens if len(token) >= 4]
    short = [token for token in tokens if len(token) == 3]
    matched_strong = [token for token in strong if token in rel_part_set or token in rel_lower]
    matched_short = [token for token in short if token in rel_part_set]

    for token in matched_strong:
        if token not in matched_tokens:
            matched_tokens.append(token)
    for token in matched_short:
        if token not in matched_tokens:
            matched_tokens.append(token)

    if matched_strong:
        score += len(matched_strong) * 2
        if len(matched_strong) >= 2:
            score += 2
        if matched_short:
            score += 1
    elif len(matched_short) >= 2:
        score += 1

    if not matched_strong and len(matched_short) <= 1 and score < 6:
        return 0, []
    return min(score, 8), matched_tokens[:4]


def _symbol_term_score(symbol: str, token: str) -> int:
    if symbol == token:
        return 14
    if len(token) >= 4 and symbol.startswith(token):
        return 8
    if len(token) >= 5 and token in symbol:
        return 4
    return 0


def _summary_term_score(summary_lower: str, term: str) -> tuple[int, list[str]]:
    normalized = " ".join(term.strip().lower().split())
    if not normalized:
        return 0, []

    if _is_symbol_like_term(normalized):
        if normalized in summary_lower:
            return 6, [normalized]
        return 0, []

    matched_tokens: list[str] = []
    score = 0
    if normalized in summary_lower and len(normalized) >= 4:
        score += 4
        matched_tokens.append(normalized)

    tokens = _structural_tokens(normalized)
    strong = [token for token in tokens if len(token) >= 4]
    short = [token for token in tokens if len(token) == 3]
    matched_strong = [token for token in strong if token in summary_lower]
    matched_short = [token for token in short if token in summary_lower]

    for token in matched_strong:
        if token not in matched_tokens:
            matched_tokens.append(token)
    for token in matched_short:
        if token not in matched_tokens:
            matched_tokens.append(token)

    score += len(matched_strong)
    if len(matched_strong) >= 2:
        score += 1
    if matched_short and matched_strong:
        score += 1

    if score <= 0:
        return 0, []
    return min(score, 6), matched_tokens[:4]


def _framework_root_candidates(profile: FrameworkProfile) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []
    for root in profile.framework_roots:
        roots.append((root, "framework"))
    for root in profile.framework_docs_roots:
        roots.append((root, "web_docs"))
    return roots


def _is_excluded_by_glob(path: Path, *, root: Path, exclude_globs: list[str]) -> bool:
    if not exclude_globs:
        return False
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    for pattern in exclude_globs:
        if fnmatch.fnmatch(rel, pattern):
            return True
    return False


def _collect_framework_local_matches(
    *,
    profile: FrameworkProfile,
    terms: list[str],
    session: ExecutionSession,
    term_weights: dict[str, int],
) -> tuple[dict[str, list[Evidence]], dict[str, SourceMetadata], list[str]]:
    results: dict[str, list[Evidence]] = {}
    source_meta: dict[str, SourceMetadata] = {}
    warnings: list[str] = []

    for root, source_type in _framework_root_candidates(profile):
        root_path = root if root.is_absolute() else root.resolve()
        if not root_path.exists() or not root_path.is_dir():
            warnings.append(f"framework path missing, skipped: {root_path}")
            continue
        session.record_effect(EffectClass.READ_ONLY, f"scan framework source root {root_path}")
        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in TEXT_FILE_EXTENSIONS:
                continue
            if _is_excluded_by_glob(file_path, root=root_path, exclude_globs=profile.exclude_globs):
                continue
            content = read_text_file(file_path, session)
            if not content:
                continue
            lines = content.splitlines()
            evidences: list[Evidence] = []
            for idx, line in enumerate(lines, start=1):
                haystack = line.lower()
                matches_in_line = [term for term in terms if _line_matches_term(haystack, term)]
                if not matches_in_line:
                    continue
                matched_term = max(matches_in_line, key=lambda item: (term_weights.get(item, 1), len(item)))
                evidences.append(
                    Evidence(
                        line=idx,
                        text=line.strip(),
                        term=matched_term,
                        source="content_match",
                        weight=max(1, term_weights.get(matched_term, 1)),
                    )
                )
                if len(evidences) >= 12:
                    break
            if not evidences:
                continue
            key = str(file_path.resolve())
            results[key] = evidences
            source_meta[key] = SourceMetadata(
                source_type=source_type,
                source_origin="framework_local_unversioned",
                framework_id=profile.profile_id,
                framework_version=profile.version,
            )
    return results, source_meta, warnings


def _collect_graph_matches(
    *,
    terms: list[str],
    term_weights: dict[str, int],
    repo_graph: dict[str, object] | None,
    framework_graphs: dict[str, dict[str, object]],
) -> tuple[dict[str, list[Evidence]], dict[str, SourceMetadata]]:
    if not terms:
        return {}, {}
    matches: dict[str, list[Evidence]] = {}
    source_meta: dict[str, SourceMetadata] = {}

    def process_graph(graph: dict[str, object], *, fallback_source_type: str, framework_ref: str | None = None) -> None:
        nodes_raw = graph.get("nodes")
        edges_raw = graph.get("edges")
        if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
            return
        node_map: dict[str, dict[str, object]] = {}
        for node in nodes_raw:
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                node_map[str(node["id"])] = node
        for edge in edges_raw:
            if not isinstance(edge, dict):
                continue
            src_id = edge.get("source")
            tgt_id = edge.get("target")
            kind = edge.get("kind")
            if not isinstance(src_id, str) or not isinstance(tgt_id, str) or not isinstance(kind, str):
                continue
            src_node = node_map.get(src_id, {})
            tgt_node = node_map.get(tgt_id, {})
            src_path = src_node.get("path") if isinstance(src_node.get("path"), str) else None
            tgt_path = tgt_node.get("path") if isinstance(tgt_node.get("path"), str) else None
            evidence_payload = edge.get("evidence")
            evidence_line = 0
            evidence_text = ""
            if isinstance(evidence_payload, list) and evidence_payload:
                first = evidence_payload[0]
                if isinstance(first, dict):
                    if isinstance(first.get("line"), int):
                        evidence_line = int(first.get("line"))
                    if isinstance(first.get("text"), str):
                        evidence_text = first.get("text") or ""
            search_blob = " ".join(
                part
                for part in [
                    str(kind),
                    str(src_path or ""),
                    str(tgt_path or ""),
                    str(edge.get("detector") or ""),
                    str(evidence_text),
                    str(tgt_node.get("package") or ""),
                ]
                if part
            ).lower()
            edge_hits = [term for term in terms if term in search_blob]
            if not edge_hits:
                continue
            best_term = max(edge_hits, key=lambda item: (term_weights.get(item, 1), len(item)))
            weight = max(1, term_weights.get(best_term, 1)) * 5
            rendered = f"graph edge {kind}: {(src_path or src_id)} -> {(tgt_path or tgt_id)}"
            for path in (src_path, tgt_path):
                if not path:
                    continue
                evidences = matches.setdefault(path, [])
                evidences.append(
                    Evidence(
                        line=evidence_line,
                        text=rendered,
                        term=best_term,
                        source="graph_match",
                        weight=weight,
                    )
                )
                if fallback_source_type == "framework" and path not in source_meta:
                    framework_id = framework_ref.split("@", 1)[0] if framework_ref else None
                    framework_version = framework_ref.split("@", 1)[1] if framework_ref and "@" in framework_ref else None
                    source_meta[path] = SourceMetadata(
                        source_type="framework",
                        source_origin="framework_graph_ref",
                        framework_id=framework_id,
                        framework_version=framework_version,
                    )
                else:
                    source_meta.setdefault(path, SourceMetadata(source_type="repo", source_origin="repo_graph_cache"))

    if repo_graph is not None:
        process_graph(repo_graph, fallback_source_type="repo")
    for ref_id, graph in framework_graphs.items():
        process_graph(graph, fallback_source_type="framework", framework_ref=ref_id)
    return matches, source_meta


def collect_matches(
    root: Path,
    terms: list[str],
    session: ExecutionSession,
    *,
    index_entry_map: dict[str, dict[str, object]],
    term_weights: dict[str, int] | None = None,
    framework_profile: FrameworkProfile | None = None,
    repo_graph: dict[str, object] | None = None,
    framework_graphs: dict[str, dict[str, object]] | None = None,
) -> tuple[dict[str, list[Evidence]], dict[str, SourceMetadata], list[str]]:
    results: dict[str, list[Evidence]] = {}
    source_meta: dict[str, SourceMetadata] = {}
    warnings: list[str] = []
    if not terms:
        return results, source_meta, warnings

    weight_map = term_weights or {}
    repo_files = iter_repo_files(root, session)
    rel_paths = [str(path.relative_to(root)) for path in repo_files]
    for file_path in repo_files:
        rel = str(file_path.relative_to(root))
        content = read_text_file(file_path, session)
        if not content:
            continue

        lines = content.splitlines()
        evidences: list[Evidence] = []
        for idx, line in enumerate(lines, start=1):
            haystack = line.lower()
            matches_in_line = [term for term in terms if _line_matches_term(haystack, term)]
            if not matches_in_line:
                continue
            matched_term = max(matches_in_line, key=lambda item: (weight_map.get(item, 1), len(item)))
            evidences.append(
                Evidence(
                    line=idx,
                    text=line.strip(),
                    term=matched_term,
                    source="content_match",
                    weight=max(1, weight_map.get(matched_term, 1)),
                )
            )
            if len(evidences) >= 12:
                break
        if evidences:
            results[rel] = evidences
            source_meta[rel] = SourceMetadata(source_type="repo", source_origin="repo")

    # Path retrieval is a first-class channel.
    path_candidates = list(index_entry_map.keys()) if index_entry_map else rel_paths
    for rel in path_candidates:
        rel_lower = rel.lower()
        path_hits: list[Evidence] = []
        for term in terms:
            score, matched_tokens = _path_term_score(rel_lower, term)
            if score <= 0:
                continue
            token_hint = ", ".join(matched_tokens) if matched_tokens else "segment"
            path_hits.append(
                Evidence(
                    line=0,
                    text=f"path overlap ({token_hint})",
                    term=term,
                    source="path_match",
                    weight=score * max(1, weight_map.get(term, 1)),
                )
            )
        if path_hits:
            existing = results.setdefault(rel, [])
            existing.extend(path_hits[:3])

    # Symbol retrieval from index metadata.
    if index_entry_map:
        structural_terms: list[tuple[str, int]] = []
        seen_terms: dict[str, int] = {}
        for term in terms:
            term_weight = max(1, weight_map.get(term, 1))
            for token in _structural_tokens(term):
                seen_terms[token] = max(seen_terms.get(token, 0), term_weight)
        structural_terms.extend(seen_terms.items())

        for rel, entry in index_entry_map.items():
            raw_symbols = entry.get("top_level_symbols")
            if not isinstance(raw_symbols, list) or not raw_symbols:
                continue
            symbols = [str(item).strip().lower() for item in raw_symbols if str(item).strip()]
            symbol_hits: list[Evidence] = []
            for token, token_weight in structural_terms:
                best_symbol = ""
                best_score = 0
                for symbol in symbols:
                    score = _symbol_term_score(symbol, token)
                    if score > best_score:
                        best_score = score
                        best_symbol = symbol
                if best_score > 0:
                    symbol_hits.append(
                        Evidence(
                            line=0,
                            text=f"symbol match: {best_symbol}",
                            term=token,
                            source="symbol_match",
                            weight=best_score * token_weight,
                        )
                    )
            if symbol_hits:
                existing = results.setdefault(rel, [])
                existing.extend(symbol_hits[:3])
                source_meta.setdefault(rel, SourceMetadata(source_type="repo", source_origin="repo"))

        # Summary retrieval from index enrichment metadata.
        for rel, entry in index_entry_map.items():
            raw_summary = entry.get("explain_summary")
            if not isinstance(raw_summary, str) or not raw_summary.strip():
                continue
            summary_lower = raw_summary.lower()
            summary_hits: list[Evidence] = []
            for term in terms:
                score, matched_tokens = _summary_term_score(summary_lower, term)
                if score <= 0:
                    continue
                token_hint = ", ".join(matched_tokens) if matched_tokens else "summary overlap"
                summary_hits.append(
                    Evidence(
                        line=0,
                        text=f"summary overlap ({token_hint})",
                        term=term,
                        source="summary_match",
                        weight=score * max(1, weight_map.get(term, 1)),
                    )
                )
            if summary_hits:
                existing = results.setdefault(rel, [])
                existing.extend(summary_hits[:3])
                source_meta.setdefault(rel, SourceMetadata(source_type="repo", source_origin="repo"))
    if framework_profile is not None:
        framework_results, framework_source_meta, framework_warnings = _collect_framework_local_matches(
            profile=framework_profile,
            terms=terms,
            session=session,
            term_weights=weight_map,
        )
        warnings.extend(framework_warnings)
        for path_key, evidences in framework_results.items():
            if path_key in results:
                continue
            results[path_key] = evidences
            source_meta[path_key] = framework_source_meta[path_key]
    graph_results, graph_source_meta = _collect_graph_matches(
        terms=terms,
        term_weights=weight_map,
        repo_graph=repo_graph,
        framework_graphs=framework_graphs or {},
    )
    for path_key, evidences in graph_results.items():
        existing = results.setdefault(path_key, [])
        existing.extend(evidences[:3])
        if path_key in graph_source_meta:
            source_meta.setdefault(path_key, graph_source_meta[path_key])
    return results, source_meta, warnings


def score_candidate(
    candidate_path: Path,
    evidences: list[Evidence],
    path_class: str,
    *,
    target_scope: str | None,
    index_explain_summary: str | None,
    question_terms: set[str],
    source_type: str,
    prefer_repo_sources: bool,
) -> int:
    content_evidences = [item for item in evidences if item.source == "content_match"]
    path_evidences = [item for item in evidences if item.source == "path_match"]
    symbol_evidences = [item for item in evidences if item.source == "symbol_match"]
    summary_evidences = [item for item in evidences if item.source == "summary_match"]
    graph_evidences = [item for item in evidences if item.source == "graph_match"]

    unique_terms = {e.term for e in content_evidences}
    # Code/config content hits are normal-strength baseline evidence.
    base = len(content_evidences) + (len(unique_terms) * 2)
    class_bonus = path_class_weight(path_class)
    score = base + class_bonus
    path_weight = sum(item.weight for item in path_evidences)
    if len(path_evidences) >= 2:
        path_weight += 3
    if path_evidences and max(item.weight for item in path_evidences) >= 6 and len(path_evidences) >= 2:
        path_weight += 2
    # Index-derived path/symbol/summary signals should rank relatively high.
    score += min(path_weight, 24)
    symbol_weight = sum(item.weight for item in symbol_evidences)
    score += min(symbol_weight, 36)
    score += min(sum(item.weight for item in summary_evidences), 12)
    score += min(sum(item.weight for item in graph_evidences), 28)
    if symbol_weight >= 14:
        score += 8

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

    # Explicit definition signatures should dominate generic lexical noise.
    symbol_tokens = {item.term.lower() for item in symbol_evidences if item.term}
    definition_hits = 0
    for evidence in content_evidences[:12]:
        line_lower = evidence.text.lower()
        for token in symbol_tokens:
            if re.search(rf"\b(def|class|function)\s+{re.escape(token)}\b", line_lower):
                definition_hits += 1
                break
    if definition_hits > 0:
        score += min(definition_hits * 14, 28)

    if index_explain_summary:
        lowered = index_explain_summary.lower()
        overlap = sum(1 for term in question_terms if term in lowered)
        score += min(overlap, 4)

    # Prefer repository-owned sources by default; keep penalties bounded.
    if source_type == "repo":
        score += 2
    elif source_type == "framework":
        score -= 3 if prefer_repo_sources else 1
    elif source_type == "web_docs":
        score -= 4 if prefer_repo_sources else 2
    elif source_type == "web_general":
        score -= 5 if prefer_repo_sources else 3
    elif source_type == "external":
        score -= 4 if prefer_repo_sources else 2

    # Docs-only hits should stay lower priority in code-target query ranking.
    if rel.startswith("docs/") or rel.endswith(".md"):
        score -= 6

    return score


def classify_source_type(
    rel_path: str,
    *,
    path_class: str,
    index_entry: dict[str, object] | None,
    source_meta: SourceMetadata | None = None,
) -> str:
    if source_meta is not None:
        return source_meta.source_type
    if index_entry and isinstance(index_entry.get("source_type"), str):
        raw = str(index_entry.get("source_type")).strip().lower()
        if raw in {"repo", "framework", "external", "web_docs", "web_general"}:
            return raw

    lowered = rel_path.lower()
    if lowered.startswith("docs/") and path_class in {"low_priority", "normal", "preferred"}:
        return "repo"
    if any(marker in lowered for marker in FRAMEWORK_PATH_MARKERS):
        return "framework"
    if any(lowered.startswith(marker) for marker in EXTERNAL_PATH_MARKERS):
        return "external"
    if path_class == "index_exclude" and lowered.startswith("vendor/"):
        return "framework"
    return "repo"


def rank_candidates(
    matches: dict[str, list[Evidence]],
    *,
    path_classes: dict[str, str],
    target_scope: str | None,
    index_entry_map: dict[str, dict[str, object]],
    question_terms: set[str],
    source_meta_map: dict[str, SourceMetadata] | None = None,
) -> list[Candidate]:
    source_meta_map = source_meta_map or {}
    preliminary_source_types: dict[str, str] = {}
    for rel_path in matches:
        path_class = path_classes.get(rel_path, "normal")
        preliminary_source_types[rel_path] = classify_source_type(
            rel_path,
            path_class=path_class,
            index_entry=index_entry_map.get(rel_path),
            source_meta=source_meta_map.get(rel_path),
        )
    prefer_repo_sources = any(value == "repo" for value in preliminary_source_types.values())

    ranked: list[Candidate] = []
    for rel_path, evidences in matches.items():
        path_class = path_classes.get(rel_path, "normal")
        source_type = preliminary_source_types.get(rel_path, "repo")
        source_meta = source_meta_map.get(rel_path)
        retrieval_sources = sorted({item.source for item in evidences})
        ranked.append(
            Candidate(
                path=Path(rel_path),
                evidences=evidences,
                score=score_candidate(
                    Path(rel_path),
                    evidences,
                    path_class,
                    target_scope=target_scope,
                    index_explain_summary=(
                        str(index_entry_map.get(rel_path, {}).get("explain_summary"))
                        if isinstance(index_entry_map.get(rel_path, {}).get("explain_summary"), str)
                        else None
                    ),
                    question_terms=question_terms,
                    source_type=source_type,
                    prefer_repo_sources=prefer_repo_sources,
                ),
                path_class=path_class,
                retrieval_sources=retrieval_sources,
                source_type=source_type,
                source_origin=source_meta.source_origin if source_meta is not None else "repo",
                framework_id=source_meta.framework_id if source_meta is not None else None,
                framework_version=source_meta.framework_version if source_meta is not None else None,
            )
        )
    ranked.sort(key=lambda c: (c.score, len(c.evidences)), reverse=True)
    return ranked


def rank_candidates_for_query(
    *,
    matches: dict[str, list[Evidence]],
    question: str,
    planner,
    index_entry_map: dict[str, dict[str, object]],
    path_classes: dict[str, str],
    source_meta_map: dict[str, SourceMetadata] | None = None,
) -> list[Candidate]:
    return rank_candidates(
        matches,
        path_classes=path_classes,
        target_scope=planner.target_scope if planner is not None else None,
        index_entry_map=index_entry_map,
        question_terms=_question_terms_for_intent(question),
        source_meta_map=source_meta_map,
    )


def _expand_matches_with_search_action(
    *,
    matches: dict[str, list[Evidence]],
    index_entry_map: dict[str, dict[str, object]],
    path_classes: dict[str, str],
    terms: list[str],
    max_new_candidates: int,
    source_scope: str,
) -> int:
    if not index_entry_map or max_new_candidates <= 0:
        return 0

    existing_paths = set(matches.keys())
    added = 0
    for rel, entry in index_entry_map.items():
        if rel in existing_paths:
            continue
        inferred_class = path_classes.get(rel, "normal")
        source_type = classify_source_type(rel, path_class=inferred_class, index_entry=entry)
        if source_scope == "repo_only" and source_type != "repo":
            continue
        if source_scope == "framework_only" and source_type != "framework":
            continue
        rel_lower = rel.lower()
        hits: list[Evidence] = []
        for term in terms:
            score, matched_tokens = _path_term_score(rel_lower, term)
            if score <= 0:
                continue
            token_hint = ", ".join(matched_tokens) if matched_tokens else "segment"
            hits.append(
                Evidence(
                    line=0,
                    text=f"search-expanded path overlap ({token_hint})",
                    term=term,
                    source="path_match",
                    weight=score,
                )
            )
        if hits:
            matches[rel] = hits[:3]
            added += 1
        if added >= max_new_candidates:
            break
    return added


def _confidence_numeric(level: str | None) -> int:
    mapping = {"low": 0, "medium": 1, "high": 2}
    return mapping.get((level or "").strip().lower(), 0)


def _top_source_counts(candidates: list[Candidate], limit: int = 5) -> tuple[int, int]:
    top = candidates[:limit]
    repo_count = sum(1 for item in top if item.source_type == "repo")
    framework_count = sum(1 for item in top if item.source_type == "framework")
    return repo_count, framework_count


def _top_candidate_snapshot(candidates: list[Candidate], limit: int = 3) -> list[str]:
    snapshot: list[str] = []
    for item in candidates[:limit]:
        snapshot.append(f"{item.path} [{item.source_type}]")
    return snapshot


def _source_distribution(candidates: list[Candidate], limit: int = 8) -> dict[str, int]:
    dist: dict[str, int] = {"repo": 0, "framework": 0, "web_docs": 0, "web_general": 0, "external": 0}
    for item in candidates[:limit]:
        if item.source_type in dist:
            dist[item.source_type] += 1
        else:
            dist[item.source_type] = dist.get(item.source_type, 0) + 1
    return dist


def compute_progress_score(
    *,
    candidates_before: list[Candidate],
    candidates_after: list[Candidate],
    evidence_count_before: int,
    evidence_count_after: int,
    top_confidence_before: str | None,
    top_confidence_after: str | None,
    threshold: float = 1.5,
) -> tuple[float, bool, dict[str, float]]:
    before_top = [str(item.path) for item in candidates_before[:5]]
    after_top = [str(item.path) for item in candidates_after[:5]]
    new_top_paths = len(set(after_top) - set(before_top))

    confidence_gain = max(
        0,
        _confidence_numeric(top_confidence_after) - _confidence_numeric(top_confidence_before),
    )
    evidence_gain = max(0, evidence_count_after - evidence_count_before)

    repo_before, framework_before = _top_source_counts(candidates_before, limit=5)
    repo_after, framework_after = _top_source_counts(candidates_after, limit=5)
    repo_gain = max(0, repo_after - repo_before)
    framework_gain = max(0, framework_after - framework_before)
    framework_drift_penalty = framework_gain if repo_gain == 0 else 0

    score = (
        (new_top_paths * 2.5)
        + (confidence_gain * 3.0)
        + (min(evidence_gain, 6) * 0.5)
        + (repo_gain * 2.0)
        - (framework_drift_penalty * 1.5)
    )
    passed = score >= threshold
    components = {
        "new_top_paths": float(new_top_paths),
        "confidence_gain": float(confidence_gain),
        "evidence_gain": float(evidence_gain),
        "repo_gain": float(repo_gain),
        "framework_gain": float(framework_gain),
        "framework_drift_penalty": float(framework_drift_penalty),
    }
    return round(score, 3), passed, components


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
        path_strength = sum(item.weight for item in candidate.evidences if item.source == "path_match")
        symbol_strength = sum(item.weight for item in candidate.evidences if item.source == "symbol_match")
        has_content = any(item.source == "content_match" for item in candidate.evidences)
        if intent_match:
            score += 4 + min(intent_overlap, 3)
        if evidence_density >= 0.75:
            score += 4
        elif evidence_density >= 0.4:
            score += 2
        if path_strength >= 10:
            score += 4
        elif path_strength >= 6:
            score += 2
        if symbol_strength >= 5:
            score += 1
        if not has_content and path_strength >= 6:
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


def _is_docs_like_candidate(candidate: Candidate) -> bool:
    rel = str(candidate.path).lower()
    if candidate.source_type in {"framework", "web_docs", "web_general"}:
        return True
    return rel.startswith("docs/") or rel.endswith(".md") or "/documentation/" in rel


def apply_ask_preset(
    candidates: list[Candidate],
    preset: str | None,
) -> tuple[list[Candidate], list[str], str]:
    if not preset or preset == "auto":
        return candidates, [], "auto"

    warnings: list[str] = []
    if preset == "repo":
        filtered = [item for item in candidates if item.source_type == "repo"]
        if not filtered:
            warnings.append("ask:repo found no repo-only hits; falling back to mixed sources")
            return candidates, warnings, "repo_fallback"
        return filtered, warnings, "repo"

    if preset == "docs":
        filtered = [item for item in candidates if _is_docs_like_candidate(item)]
        if not filtered:
            warnings.append("ask:docs found no docs/framework hits; falling back to mixed sources")
            return candidates, warnings, "docs_fallback"
        return filtered, warnings, "docs"

    if preset == "latest":
        warnings.append("ask:latest web retrieval is not implemented yet; using docs-focused fallback")
        filtered = [item for item in candidates if _is_docs_like_candidate(item)]
        if not filtered:
            warnings.append("ask:latest fallback found no docs/framework hits; falling back to mixed sources")
            return candidates, warnings, "latest_fallback_mixed"
        return filtered, warnings, "latest_fallback_docs"

    warnings.append(f"unknown ask preset '{preset}'; using default query ranking")
    return candidates, warnings, "unknown_fallback"


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
                f"(score={candidate.score}, class={candidate.path_class}, matches={len(candidate.evidences)}, "
                f"sources={','.join(candidate.retrieval_sources)}, source_type={candidate.source_type}, "
                f"source_origin={candidate.source_origin}, framework_id={candidate.framework_id or '-'}, "
                f"framework_version={candidate.framework_version or '-'})"
            )
        else:
            print(f"{idx}. {candidate.path} ({len(candidate.evidences)} matches)")

    if not is_compact(view):
        print("\n--- Why ---")
        evidence_candidate_limit = 2 if view == "standard" else 5
        evidence_line_limit = 2 if view == "standard" else 3
        for candidate in candidates[:evidence_candidate_limit]:
            for evidence in candidate.evidences[:evidence_line_limit]:
                if evidence.line > 0:
                    print(
                        f"{candidate.path}:{evidence.line}: {evidence.text} "
                        f"[term={evidence.term}; source={evidence.source}]"
                    )
                else:
                    print(f"{candidate.path}: {evidence.text} [term={evidence.term}; source={evidence.source}]")

    print("\n--- Next Step ---")
    if candidates[0].source_type == "repo":
        print(f"Run: forge explain {candidates[0].path}")
    else:
        print("Top hit is non-repo source; narrow query for repo-local implementation details.")


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
        focus_lines = [e.line for e in candidate.evidences[:2] if e.line > 0]
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
    ask_mode = bool(getattr(args, "ask_mode", False))
    ask_command = str(getattr(args, "ask_command", "") or "")
    ask_preset_requested = str(getattr(args, "ask_preset", "") or "") or None
    ask_guided = bool(getattr(args, "ask_guided", False))
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
        effective_planner_terms = compose_planner_terms(
            planner.lead_terms,
            planner.support_terms,
            planner.search_terms,
        )
        terms = derive_search_terms(
            question,
            request.profile,
            cross_lingual,
            planner_terms=effective_planner_terms,
        )
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

    framework_registry = load_framework_registry(repo_root, session)
    requested_framework_profile = getattr(args, "framework_profile", None)
    framework_profile, framework_profile_id, framework_warnings = select_framework_profile(
        framework_registry,
        requested_framework_profile,
    )
    if not is_json and is_full(view):
        if framework_profile is not None:
            print(
                "Framework profile: "
                f"{framework_profile.profile_id} "
                f"(version={framework_profile.version or '-'}, "
                f"roots={len(framework_profile.framework_roots)}, docs_roots={len(framework_profile.framework_docs_roots)})"
            )
        elif framework_registry.exists:
            print("Framework profile: none selected")

    repo_graph = load_repo_graph(repo_root, session)
    framework_graphs, framework_graph_warnings = load_framework_graph_references(repo_root, session)
    framework_warnings.extend(framework_graph_warnings)
    if repo_graph is None:
        if request.profile in {Profile.STANDARD, Profile.DETAILED}:
            framework_warnings.append("graph cache missing (.forge/graph.json); continuing with lexical/index retrieval")

    if not is_json and is_full(view):
        print(f"Search terms: {', '.join(terms[:8])}" if terms else "Search terms: none")
    term_weights = build_term_weight_map(terms)
    matches, source_meta_map, source_warnings = collect_matches(
        repo_root,
        terms,
        session,
        index_entry_map=index_entry_map,
        term_weights=term_weights,
        framework_profile=framework_profile,
        repo_graph=repo_graph,
        framework_graphs=framework_graphs,
    )
    framework_warnings.extend(source_warnings)
    candidates = rank_candidates_for_query(
        matches=matches,
        question=question,
        planner=planner,
        index_entry_map=index_entry_map,
        path_classes=path_classes,
        source_meta_map=source_meta_map,
    )
    explain_feedback = build_explain_feedback(question=question, candidates=candidates[:12])
    candidates = rerank_with_explain_feedback(candidates, explain_feedback)
    ask_warnings: list[str] = []
    ask_preset_effective = "auto"
    candidates, ask_warnings, ask_preset_effective = apply_ask_preset(candidates, ask_preset_requested)
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
                    "source": item.source,
                    "retrieval_source": item.source,
                    "source_type": candidate.source_type,
                    "source_origin": candidate.source_origin,
                    "framework_id": candidate.framework_id,
                    "framework_version": candidate.framework_version,
                }
            )
    orchestration_decisions = []
    orchestration_iterations: list[QueryOrchestrationIteration] = []
    orchestration_done_reason = "running"
    orchestration_usage: dict[str, object] = {}
    orchestration_fallback_reason: str | None = None
    adaptive_continue_triggered = False
    no_progress_streak = 0
    no_progress_streak_limit = 2
    search_noop_streak = 0
    progress_threshold = 1.5
    budget_tokens_used = 0
    budget_files_used = 0
    loop_started = time.perf_counter()

    for iteration_idx in range(1, llm_settings.query_orchestrator_max_iterations + 1):
        elapsed_ms = int((time.perf_counter() - loop_started) * 1000)
        if elapsed_ms >= llm_settings.query_orchestrator_max_wall_time_ms:
            orchestration_done_reason = "budget_exhausted"
            break

        candidate_count_before = len(candidates)
        evidence_count_before = len(evidence_payload)
        candidates_before_snapshot = list(candidates)
        budget_tokens_before = budget_tokens_used
        budget_files_before = budget_files_used
        top_candidates_before = _top_candidate_snapshot(candidates_before_snapshot)
        source_distribution_before = _source_distribution(candidates_before_snapshot)
        feedback_by_path = {str(item.path): item for item in explain_feedback}
        top_feedback = feedback_by_path.get(str(candidates[0].path)) if candidates else None
        top_confidence_before = top_feedback.linkage_confidence if top_feedback is not None else None
        adaptive_continue = bool(top_feedback is not None and top_feedback.linkage_confidence == "low" and len(candidates) > 1)
        if adaptive_continue:
            adaptive_continue_triggered = True

        outcome = maybe_orchestrate_query_actions(
            capability=request.capability,
            profile=request.profile,
            question=question,
            candidate_paths=[str(item.path) for item in candidates[:12]],
            evidence_count=len(evidence_payload),
            iteration=iteration_idx,
            settings=llm_settings,
            repo_root=repo_root,
        )
        orchestration_usage = outcome.usage
        if outcome.fallback_reason:
            orchestration_fallback_reason = outcome.fallback_reason
        if outcome.decisions:
            orchestration_decisions.extend(outcome.decisions)

        decision = outcome.decisions[0].decision if outcome.decisions else "stop"
        next_action = outcome.decisions[0].next_action if outcome.decisions else None
        reason = (
            outcome.decisions[0].reason
            if outcome.decisions
            else str(outcome.fallback_reason or "no orchestration decision produced")
        )
        confidence = outcome.decisions[0].confidence if outcome.decisions else "medium"
        iteration_fallback_trigger = outcome.fallback_reason

        if (
            decision == "continue"
            and next_action == "search"
            and search_noop_streak >= 1
            and candidates
            and budget_files_used < llm_settings.query_orchestrator_max_files
        ):
            next_action = "read"
            reason = f"{reason} (deterministic anti-stall override: repeated search-noop switched to read)"

        if outcome.done_reason in {"policy_blocked", "budget_exhausted"} and not outcome.decisions:
            orchestration_done_reason = outcome.done_reason
            orchestration_iterations.append(
                QueryOrchestrationIteration(
                    iteration=iteration_idx,
                    decision=decision,
                    next_action=next_action,
                    reason=reason,
                    confidence=confidence,
                    done_reason=orchestration_done_reason,
                    evidence_count_before=evidence_count_before,
                    evidence_count_after=len(evidence_payload),
                    candidate_count_before=candidate_count_before,
                    candidate_count_after=len(candidates),
                    budget_tokens_before=budget_tokens_before,
                    budget_tokens_after=budget_tokens_used,
                    budget_files_before=budget_files_before,
                    budget_files_after=budget_files_used,
                    budget_tokens_used=budget_tokens_used,
                    budget_files_used=budget_files_used,
                    elapsed_ms=int((time.perf_counter() - loop_started) * 1000),
                    handler_status="blocked",
                    handler_detail="decision not executable due to policy/budget block before handler stage",
                    top_candidates_before=top_candidates_before,
                    top_candidates_after=_top_candidate_snapshot(candidates),
                    source_distribution_before=source_distribution_before,
                    source_distribution_after=_source_distribution(candidates),
                    source_scope="none",
                    source_scope_reason="decision blocked before handler execution",
                    source_caps={
                        "remaining_files_before": max(0, llm_settings.query_orchestrator_max_files - budget_files_before),
                        "remaining_tokens_before": max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_before),
                        "remaining_files_after": max(0, llm_settings.query_orchestrator_max_files - budget_files_used),
                        "remaining_tokens_after": max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_used),
                        "framework_top_before": source_distribution_before.get("framework", 0),
                        "framework_top_after": _source_distribution(candidates).get("framework", 0),
                        "framework_expansion_allowed": False,
                    },
                    fallback_trigger=iteration_fallback_trigger,
                    blocked_reason=reason,
                    progress_score=0.0,
                    progress_passed=False,
                    progress_components={},
                )
            )
            break

        if decision == "stop":
            orchestration_done_reason = "sufficient_evidence"
            orchestration_iterations.append(
                QueryOrchestrationIteration(
                    iteration=iteration_idx,
                    decision=decision,
                    next_action=next_action,
                    reason=reason,
                    confidence=confidence,
                    done_reason=orchestration_done_reason,
                    evidence_count_before=evidence_count_before,
                    evidence_count_after=len(evidence_payload),
                    candidate_count_before=candidate_count_before,
                    candidate_count_after=len(candidates),
                    budget_tokens_before=budget_tokens_before,
                    budget_tokens_after=budget_tokens_used,
                    budget_files_before=budget_files_before,
                    budget_files_after=budget_files_used,
                    budget_tokens_used=budget_tokens_used,
                    budget_files_used=budget_files_used,
                    elapsed_ms=int((time.perf_counter() - loop_started) * 1000),
                    handler_status="stop",
                    handler_detail="decision requested stop before handler stage",
                    top_candidates_before=top_candidates_before,
                    top_candidates_after=_top_candidate_snapshot(candidates),
                    source_distribution_before=source_distribution_before,
                    source_distribution_after=_source_distribution(candidates),
                    source_scope="none",
                    source_scope_reason="decision requested stop before handler execution",
                    source_caps={
                        "remaining_files_before": max(0, llm_settings.query_orchestrator_max_files - budget_files_before),
                        "remaining_tokens_before": max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_before),
                        "remaining_files_after": max(0, llm_settings.query_orchestrator_max_files - budget_files_used),
                        "remaining_tokens_after": max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_used),
                        "framework_top_before": source_distribution_before.get("framework", 0),
                        "framework_top_after": _source_distribution(candidates).get("framework", 0),
                        "framework_expansion_allowed": False,
                    },
                    fallback_trigger=iteration_fallback_trigger,
                    blocked_reason=None,
                    progress_score=0.0,
                    progress_passed=True,
                    progress_components={},
                )
            )
            break

        action_applied = False
        handler_status = "ok"
        handler_detail = "no action executed"
        source_scope = "repo_only"
        source_scope_reason = "default repo-first scope"

        if next_action == "search":
            # Deterministically expand candidate pool via path-based index hints.
            source_scope = "repo_only"
            top_repo_candidates = sum(1 for item in candidates[:5] if item.source_type == "repo")
            if top_repo_candidates <= 1:
                source_scope = "all"
                source_scope_reason = "scope widened because top repo candidates are weak"
            else:
                source_scope_reason = "scope kept repo-only because repo candidates are sufficient"
            added_candidates = _expand_matches_with_search_action(
                matches=matches,
                index_entry_map=index_entry_map,
                path_classes=path_classes,
                terms=terms,
                max_new_candidates=min(12, llm_settings.query_orchestrator_max_files),
                source_scope=source_scope,
            )
            if added_candidates > 0:
                candidates = rank_candidates_for_query(
                    matches=matches,
                    question=question,
                    planner=planner,
                    index_entry_map=index_entry_map,
                    path_classes=path_classes,
                    source_meta_map=source_meta_map,
                )
                explain_feedback = build_explain_feedback(question=question, candidates=candidates[:12])
                candidates = rerank_with_explain_feedback(candidates, explain_feedback)
                candidates, extra_ask_warnings, ask_preset_effective = apply_ask_preset(
                    candidates,
                    ask_preset_requested,
                )
                if extra_ask_warnings:
                    ask_warnings.extend(extra_ask_warnings)
                explain_feedback = build_explain_feedback(question=question, candidates=candidates[:12])
                candidates = rerank_with_explain_feedback(candidates, explain_feedback)
                action_applied = True
                budget_tokens_used += min(added_candidates * 20, 240)
                handler_detail = f"search expanded candidate pool by {added_candidates} path-hint matches (scope={source_scope})"
            else:
                handler_status = "noop"
                handler_detail = "search found no additional bounded candidates"

        elif next_action == "read":
            if not candidates:
                handler_status = "noop"
                handler_detail = "read skipped because no candidates are available"
                source_scope = "none"
                source_scope_reason = "no candidates available for read"
            else:
                remaining_files = max(0, llm_settings.query_orchestrator_max_files - budget_files_used)
                remaining_tokens = max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_used)
                if remaining_files <= 0 or remaining_tokens <= 0:
                    orchestration_done_reason = "budget_exhausted"
                    handler_status = "budget_blocked"
                    handler_detail = "read skipped because budget is exhausted"
                    source_scope = "none"
                    source_scope_reason = "read denied by budget caps"
                else:
                    start_idx = 1 if adaptive_continue else 0
                    # enrich_detailed_context reads at most three candidates per call.
                    max_read_batch = 3
                    inspect_size = max(1, min(len(candidates) - start_idx, remaining_files, max_read_batch))
                    inspect_slice = candidates[start_idx : start_idx + inspect_size]
                    if inspect_slice:
                        if all(item.source_type == "repo" for item in inspect_slice):
                            source_scope = "repo_only"
                        elif all(item.source_type == "framework" for item in inspect_slice):
                            source_scope = "framework_only"
                        else:
                            source_scope = "mixed"
                        source_scope_reason = "read scope derived from selected candidate slice"
                    budget_files_used += len(inspect_slice)
                    bounded_details = enrich_detailed_context(repo_root, inspect_slice, session)
                    extra_limit = min(len(bounded_details), remaining_tokens // 40)
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
                                "source": "content_match",
                                "retrieval_source": "content_match",
                            }
                        )
                        action_applied = True
                    budget_tokens_used += extra_limit * 40
                    if bounded_details:
                        detailed_lines.extend(bounded_details[:12])
                    if action_applied:
                        handler_detail = f"read collected {extra_limit} bounded context lines"
                    else:
                        handler_status = "noop"
                        handler_detail = "read executed but produced no parseable evidence lines"

        elif next_action == "explain":
            if not candidates:
                handler_status = "noop"
                handler_detail = "explain skipped because no candidates are available"
                source_scope = "none"
                source_scope_reason = "no candidates available for explain"
            else:
                explain_feedback = build_explain_feedback(question=question, candidates=candidates[:12])
                candidates = rerank_with_explain_feedback(candidates, explain_feedback)
                action_applied = True
                budget_tokens_used += min(80, llm_settings.query_orchestrator_max_tokens // 8)
                handler_detail = "explain feedback recomputed for top candidates"
                source_scope = "top_candidates"
                source_scope_reason = "explain ran on bounded top candidate set"

        elif next_action == "rank":
            candidates = rerank_with_explain_feedback(candidates, explain_feedback)
            action_applied = True
            handler_detail = "rank recomputed candidate order from current explain feedback"
            source_scope = "all_candidates"
            source_scope_reason = "rank evaluated current candidate list"

        elif next_action == "summarize":
            orchestration_done_reason = "sufficient_evidence"
            action_applied = True
            handler_detail = "summarize requested finalization"
            source_scope = "none"
            source_scope_reason = "summarize finalizes without retrieval expansion"

        elif next_action == "stop":
            orchestration_done_reason = "sufficient_evidence"
            action_applied = True
            handler_detail = "stop requested finalization"
            source_scope = "none"
            source_scope_reason = "stop finalizes without retrieval expansion"

        else:
            orchestration_done_reason = "policy_blocked"
            handler_status = "invalid_action"
            handler_detail = f"unsupported action '{next_action}'"
            source_scope = "none"
            source_scope_reason = "unsupported action blocked by policy"

        feedback_after = {str(item.path): item for item in explain_feedback}
        top_feedback_after = feedback_after.get(str(candidates[0].path)) if candidates else None
        top_confidence_after = top_feedback_after.linkage_confidence if top_feedback_after is not None else None
        progress_score, progress_passed, progress_components = compute_progress_score(
            candidates_before=candidates_before_snapshot,
            candidates_after=candidates,
            evidence_count_before=evidence_count_before,
            evidence_count_after=len(evidence_payload),
            top_confidence_before=top_confidence_before,
            top_confidence_after=top_confidence_after,
            threshold=progress_threshold,
        )
        if progress_passed:
            no_progress_streak = 0
        else:
            no_progress_streak += 1

        top_candidates_after = _top_candidate_snapshot(candidates)
        source_distribution_after = _source_distribution(candidates)
        source_caps = {
            "remaining_files_before": max(0, llm_settings.query_orchestrator_max_files - budget_files_before),
            "remaining_tokens_before": max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_before),
            "remaining_files_after": max(0, llm_settings.query_orchestrator_max_files - budget_files_used),
            "remaining_tokens_after": max(0, llm_settings.query_orchestrator_max_tokens - budget_tokens_used),
            "framework_top_before": source_distribution_before.get("framework", 0),
            "framework_top_after": source_distribution_after.get("framework", 0),
            "framework_expansion_allowed": source_scope in {"all", "framework_only", "mixed"},
        }

        if orchestration_done_reason in {"policy_blocked", "budget_exhausted", "sufficient_evidence"} and (
            next_action in {"summarize"} or not action_applied and next_action not in {"search", "read", "explain", "rank"}
        ):
            orchestration_iterations.append(
                QueryOrchestrationIteration(
                    iteration=iteration_idx,
                    decision=decision,
                    next_action=next_action,
                    reason=reason,
                    confidence=confidence,
                    done_reason=orchestration_done_reason,
                    evidence_count_before=evidence_count_before,
                    evidence_count_after=len(evidence_payload),
                    candidate_count_before=candidate_count_before,
                    candidate_count_after=len(candidates),
                    budget_tokens_before=budget_tokens_before,
                    budget_tokens_after=budget_tokens_used,
                    budget_files_before=budget_files_before,
                    budget_files_after=budget_files_used,
                    budget_tokens_used=budget_tokens_used,
                    budget_files_used=budget_files_used,
                    elapsed_ms=int((time.perf_counter() - loop_started) * 1000),
                    handler_status=handler_status,
                    handler_detail=handler_detail,
                    top_candidates_before=top_candidates_before,
                    top_candidates_after=top_candidates_after,
                    source_distribution_before=source_distribution_before,
                    source_distribution_after=source_distribution_after,
                    source_scope=source_scope,
                    source_scope_reason=source_scope_reason,
                    source_caps=source_caps,
                    fallback_trigger=iteration_fallback_trigger,
                    blocked_reason=reason if orchestration_done_reason == "policy_blocked" else None,
                    progress_score=progress_score,
                    progress_passed=progress_passed,
                    progress_components=progress_components,
                )
            )
            break

        if no_progress_streak >= no_progress_streak_limit:
            orchestration_done_reason = "no_progress"

        if next_action == "search" and handler_status == "noop":
            search_noop_streak += 1
        else:
            search_noop_streak = 0

        elapsed_after_ms = int((time.perf_counter() - loop_started) * 1000)
        if elapsed_after_ms >= llm_settings.query_orchestrator_max_wall_time_ms:
            orchestration_done_reason = "budget_exhausted"
        if budget_tokens_used >= llm_settings.query_orchestrator_max_tokens:
            orchestration_done_reason = "budget_exhausted"
        if budget_files_used >= llm_settings.query_orchestrator_max_files:
            orchestration_done_reason = "budget_exhausted"

        orchestration_iterations.append(
            QueryOrchestrationIteration(
                iteration=iteration_idx,
                decision=decision,
                next_action=next_action,
                reason=reason,
                confidence=confidence,
                done_reason=orchestration_done_reason,
                evidence_count_before=evidence_count_before,
                evidence_count_after=len(evidence_payload),
                candidate_count_before=candidate_count_before,
                candidate_count_after=len(candidates),
                budget_tokens_before=budget_tokens_before,
                budget_tokens_after=budget_tokens_used,
                budget_files_before=budget_files_before,
                budget_files_after=budget_files_used,
                budget_tokens_used=budget_tokens_used,
                budget_files_used=budget_files_used,
                elapsed_ms=elapsed_after_ms,
                handler_status=handler_status,
                handler_detail=handler_detail,
                top_candidates_before=top_candidates_before,
                top_candidates_after=top_candidates_after,
                source_distribution_before=source_distribution_before,
                source_distribution_after=source_distribution_after,
                source_scope=source_scope,
                source_scope_reason=source_scope_reason,
                source_caps=source_caps,
                fallback_trigger=iteration_fallback_trigger,
                blocked_reason=reason if orchestration_done_reason == "policy_blocked" else None,
                progress_score=progress_score,
                progress_passed=progress_passed,
                progress_components=progress_components,
            )
        )

        if orchestration_done_reason in {"budget_exhausted", "policy_blocked", "sufficient_evidence", "no_progress"}:
            break
    else:
        orchestration_done_reason = "budget_exhausted"

    if not orchestration_usage:
        orchestration_usage = {
            "enabled": llm_settings.query_orchestrator_enabled,
            "mode": llm_settings.query_orchestrator_mode,
            "fallback_reason": "query action orchestrator not attempted",
        }
    if orchestration_fallback_reason:
        orchestration_usage["fallback_reason"] = orchestration_fallback_reason

    feedback_by_path = {str(item.path): item for item in explain_feedback}
    top_feedback = feedback_by_path.get(str(candidates[0].path)) if candidates else None

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
    if orchestration_done_reason == "budget_exhausted":
        uncertainty.append("Query action orchestration hit configured budget limits.")
    if orchestration_done_reason == "policy_blocked":
        uncertainty.append("Query action orchestration decision was rejected; deterministic fallback was used.")
    if orchestration_done_reason == "no_progress":
        uncertainty.append("Query action orchestration stopped after repeated no-progress iterations.")
    if ask_guided:
        ask_warnings.append("--guided is not implemented yet in this rollout; running deterministic ask preset flow")
    deduped_ask_warnings: list[str] = []
    seen_ask_warnings: set[str] = set()
    for warning in ask_warnings:
        norm = warning.strip()
        if not norm or norm in seen_ask_warnings:
            continue
        seen_ask_warnings.add(norm)
        deduped_ask_warnings.append(norm)
    ask_warnings = deduped_ask_warnings
    for warning in ask_warnings:
        uncertainty.append(f"Ask preset warning: {warning}")
    for warning in framework_warnings:
        uncertainty.append(f"Framework profile warning: {warning}")
    next_step = (
        f"Run: forge explain {candidates[0].path}"
        if candidates and candidates[0].source_type == "repo"
        else "Top hit is non-repo source; narrow query for repo-local implementation details."
        if candidates
        else "Try a narrower question with a concrete symbol or path fragment."
    )
    if not is_json:
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
    else:
        llm_outcome = None

    sections: dict[str, object] = {
        "likely_locations": [
            {
                "path": str(candidate.path),
                "score": candidate.score,
                "path_class": candidate.path_class,
                "matches": len(candidate.evidences),
                "retrieval_sources": candidate.retrieval_sources,
                "source_type": candidate.source_type,
                "source_origin": candidate.source_origin,
                "framework_id": candidate.framework_id,
                "framework_version": candidate.framework_version,
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
        "llm_usage": (
            llm_outcome.usage
            if llm_outcome is not None
            else {
                "policy": "off",
                "mode": llm_settings.mode,
                "attempted": False,
                "used": False,
                "fallback_reason": "summary refinement disabled for json output",
            }
        ),
        "provenance": provenance_section(
            llm_used=bool(llm_outcome.usage.get("used")) if llm_outcome is not None else False,
            evidence_count=len(evidence_payload),
        ),
        "framework_profile": {
            "requested": requested_framework_profile,
            "resolved": framework_profile_id,
            "config_path": str(framework_registry.config_path),
            "config_present": framework_registry.exists,
            "default_profile": framework_registry.default_profile,
            "warnings": framework_warnings,
            "framework_id": framework_profile.profile_id if framework_profile is not None else None,
            "framework_version": framework_profile.version if framework_profile is not None else None,
            "framework_roots": [str(path) for path in (framework_profile.framework_roots if framework_profile is not None else [])],
            "framework_docs_roots": [
                str(path) for path in (framework_profile.framework_docs_roots if framework_profile is not None else [])
            ],
        },
        "graph_usage": {
            "repo_graph_loaded": repo_graph is not None,
            "framework_graph_refs_loaded": sorted(framework_graphs.keys()),
        },
        "ask": {
            "enabled": ask_mode,
            "command": ask_command if ask_mode else None,
            "preset_requested": ask_preset_requested,
            "preset_effective": ask_preset_effective,
            "guided_requested": ask_guided,
            "warnings": ask_warnings,
        },
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
            "lead_terms": planner.lead_terms if planner is not None else [],
            "support_terms": planner.support_terms if planner is not None else [],
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
            "progress_policy": {
                "threshold": progress_threshold,
                "no_progress_streak_limit": no_progress_streak_limit,
            },
            "decisions": [
                {
                    "decision": d.decision,
                    "next_action": d.next_action,
                    "reason": d.reason,
                    "confidence": d.confidence,
                }
                for d in orchestration_decisions
            ],
            "iterations": [
                {
                    "iteration": item.iteration,
                    "decision": item.decision,
                    "next_action": item.next_action,
                    "reason": item.reason,
                    "confidence": item.confidence,
                    "done_reason": item.done_reason,
                    "evidence_count_before": item.evidence_count_before,
                    "evidence_count_after": item.evidence_count_after,
                    "candidate_count_before": item.candidate_count_before,
                    "candidate_count_after": item.candidate_count_after,
                    "budget_tokens_before": item.budget_tokens_before,
                    "budget_tokens_after": item.budget_tokens_after,
                    "budget_files_before": item.budget_files_before,
                    "budget_files_after": item.budget_files_after,
                    "budget_tokens_used": item.budget_tokens_used,
                    "budget_files_used": item.budget_files_used,
                    "elapsed_ms": item.elapsed_ms,
                    "handler_status": item.handler_status,
                    "handler_detail": item.handler_detail,
                    "top_candidates_before": item.top_candidates_before,
                    "top_candidates_after": item.top_candidates_after,
                    "source_distribution_before": item.source_distribution_before,
                    "source_distribution_after": item.source_distribution_after,
                    "source_scope": item.source_scope,
                    "source_scope_reason": item.source_scope_reason,
                    "source_caps": item.source_caps,
                    "fallback_trigger": item.fallback_trigger,
                    "blocked_reason": item.blocked_reason,
                    "progress_score": item.progress_score,
                    "progress_passed": item.progress_passed,
                    "progress_components": item.progress_components,
                }
                for item in orchestration_iterations
            ],
            "done_reason": orchestration_done_reason,
            "usage": orchestration_usage,
            "adaptive_continuation_triggered": adaptive_continue_triggered,
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
        if planner is not None and planner.lead_terms:
            print(f"Lead terms: {', '.join(planner.lead_terms[:8])}")
        if planner is not None and planner.support_terms:
            print(f"Support terms: {', '.join(planner.support_terms[:8])}")
        if planner is not None and planner.code_variants:
            print(f"Code variants: {', '.join(planner.code_variants[:8])}")
        if planner_usage.get("fallback_reason"):
            print(f"Fallback: {planner_usage['fallback_reason']}")

        if ask_mode:
            print("\n--- Ask Preset ---")
            print(f"Command: {ask_command or 'ask'}")
            print(f"Preset requested: {ask_preset_requested or 'auto'}")
            print(f"Preset effective: {ask_preset_effective}")
            print(f"Guided requested: {ask_guided}")
            for warning in ask_warnings[:8]:
                print(f"Warning: {warning}")

        print("\n--- Framework Profile ---")
        print(f"Config present: {framework_registry.exists}")
        print(f"Requested: {requested_framework_profile or '-'}")
        print(f"Resolved: {framework_profile_id or '-'}")
        if framework_profile is not None:
            print(f"Framework ID: {framework_profile.profile_id}")
            print(f"Framework version: {framework_profile.version or '-'}")
            print(f"Framework roots: {len(framework_profile.framework_roots)}")
            print(f"Framework docs roots: {len(framework_profile.framework_docs_roots)}")
        if framework_warnings:
            for warning in framework_warnings[:8]:
                print(f"Warning: {warning}")

        print("\n--- Action Orchestration ---")
        print(f"Done reason: {orchestration_done_reason}")
        if orchestration_decisions:
            for idx, decision in enumerate(orchestration_decisions, start=1):
                print(
                    f"{idx}. decision={decision.decision} "
                    f"next_action={decision.next_action or '-'} "
                    f"confidence={decision.confidence}"
                )
                print(f"   reason: {decision.reason}")
        if orchestration_iterations:
            print("Iterations:")
            for item in orchestration_iterations:
                print(
                    f"- #{item.iteration}: decision={item.decision} next_action={item.next_action or '-'} "
                    f"done={item.done_reason} evidence={item.evidence_count_before}->{item.evidence_count_after} "
                    f"candidates={item.candidate_count_before}->{item.candidate_count_after} "
                    f"files={item.budget_files_before}->{item.budget_files_after} "
                    f"tokens~={item.budget_tokens_before}->{item.budget_tokens_after} "
                    f"elapsed_ms={item.elapsed_ms} handler={item.handler_status} "
                    f"scope={item.source_scope} progress={item.progress_score:.2f}"
                )
                print(f"  detail: {item.handler_detail}")
                print(f"  scope_reason: {item.source_scope_reason}")
                print(
                    "  top_before: "
                    + (", ".join(item.top_candidates_before) if item.top_candidates_before else "-")
                )
                print(
                    "  top_after: "
                    + (", ".join(item.top_candidates_after) if item.top_candidates_after else "-")
                )
                print(
                    "  source_dist: "
                    f"before={item.source_distribution_before} after={item.source_distribution_after}"
                )
                print(f"  source_caps: {item.source_caps}")
                if item.progress_components:
                    comps = ", ".join(
                        f"{k}={v:g}" for k, v in item.progress_components.items()
                    )
                    print(f"  progress_components: {comps}")
                if item.fallback_trigger:
                    print(f"  fallback_trigger: {item.fallback_trigger}")
                if item.blocked_reason:
                    print(f"  blocked_reason: {item.blocked_reason}")
        if orchestration_usage.get("fallback_reason"):
            print(f"Fallback: {orchestration_usage['fallback_reason']}")

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
