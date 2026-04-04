from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import (
    RelatedTarget,
    ResolvedTarget,
    load_index_entry_map,
    load_index_path_class_map,
    path_class_weight,
    prioritize_paths_by_index,
    rank_related_targets,
    resolve_file_or_symbol_target,
)
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.explain_analysis_foundation import (
    DefaultValueSignal,
    Evidence,
    LLMParticipation,
    OutputSurface,
    SettingsInfluence,
    SymbolFact,
    confidence_for_hits,
    extract_default_values,
    extract_llm_participation,
    extract_output_surfaces,
    extract_settings_influences,
    extract_symbol_facts,
)
from core.framework_profiles import load_framework_registry, select_framework_profile
from core.graph_cache import load_framework_graph_references, load_repo_graph
from core.llm_integration import maybe_refine_summary, provenance_section, resolve_settings
from core.mode_orchestrator import iter_bounded_cycles
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.repo_io import iter_repo_files, read_text_file
from core.run_reference import RunReferenceError, resolve_from_run_payload


@dataclass
class InferencePoint:
    inference_id: str
    inference: str
    evidence_ids: list[str]
    rationale: str
    confidence: str


@dataclass
class Edge:
    source_path: str
    target_path: str | None
    target_raw: str | None
    edge_kind: str
    evidence: Evidence
    confidence: str
    source_type: str
    target_type: str
    framework_id: str | None = None
    framework_version: str | None = None


BEHAVIOR_SIGNAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("guard_return", re.compile(r"^\s*if\s+not\s+.+:\s*$")),
    ("filesystem_mkdir", re.compile(r"\.mkdir\(")),
    ("filesystem_write", re.compile(r"\.write_text\(")),
    ("file_append", re.compile(r"\.open\(\s*[\"']a[\"']")),
    ("serialization_json", re.compile(r"\bjson\.dumps\(")),
    ("secret_redaction", re.compile(r"\.pop\(\s*[\"'](api_key|authorization|prompt|user_prompt|system_prompt)[\"']")),
]


ROLE_MARKERS = {
    "entrypoint": ["if __name__ == \"__main__\":", "argparse.ArgumentParser(", "main("],
    "configuration": [".yml", ".yaml", ".toml", ".ini", "config", "settings"],
    "support code": ["helper", "util", "common", "shared", "support"],
}


def _resolve_runtime_int(
    args,
    key: str,
    default: int,
    *,
    min_value: int = 1,
    max_value: int = 200,
) -> tuple[int, str]:
    values = getattr(args, "runtime_settings_values", {})
    sources = getattr(args, "runtime_settings_sources", {})
    raw = values.get(key) if isinstance(values, dict) else None
    source = str(sources.get(key) or "default") if isinstance(sources, dict) else "default"
    if raw is None:
        return default, "default"
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return default, "default"
    if parsed < min_value or parsed > max_value:
        return default, "default"
    return parsed, source


def classify_role(rel_path: Path, content: str, index_entry: dict[str, object] | None) -> tuple[str, str]:
    lowered_path = str(rel_path).lower()
    lowered_content = content.lower()

    if any(marker in content for marker in ROLE_MARKERS["entrypoint"]):
        return "entrypoint", "contains explicit startup/CLI entry markers"

    if "config" in lowered_path or any(ext in lowered_path for ext in [".yml", ".yaml", ".toml", ".ini"]):
        return "configuration", "path/extension suggests configuration data"

    if index_entry:
        path_class = index_entry.get("path_class")
        if isinstance(path_class, str) and path_class_weight(path_class) >= 3:
            return "implementation", "indexed as structurally preferred path"
        symbols = index_entry.get("top_level_symbols")
        if isinstance(symbols, list) and symbols:
            if len(symbols) >= 3:
                return "implementation", "contains multiple top-level symbols"

    if any(marker in lowered_path or marker in lowered_content for marker in ROLE_MARKERS["support code"]):
        return "support code", "path/content suggests helper or utility responsibilities"

    return "implementation", "default classification from executable/source structure"


def gather_evidence_for_target(
    target: ResolvedTarget,
    request: CommandRequest,
) -> list[Evidence]:
    lines = target.content.splitlines()
    evidence: list[Evidence] = []
    rel_path = target.path

    if target.source == "symbol":
        symbol = request.payload.strip()
        symbol_patterns = [
            re.compile(rf"^\s*def\s+{re.escape(symbol)}\s*\("),
            re.compile(rf"^\s*class\s+{re.escape(symbol)}\s*[\(:]"),
        ]
        for idx, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in symbol_patterns):
                evidence.append(Evidence(path=rel_path, line=idx, text=line.strip()))
                for extra in range(1, 3):
                    if idx - 1 + extra < len(lines):
                        evidence.append(
                            Evidence(
                                path=rel_path,
                                line=idx + extra,
                                text=lines[idx - 1 + extra].strip(),
                            )
                        )
                break

    structural_patterns = [
        re.compile(r"^\s*class\s+\w+"),
        re.compile(r"^\s*def\s+\w+"),
        re.compile(r"^\s*import\s+"),
        re.compile(r"^\s*from\s+\w+\s+import\s+"),
        re.compile(r"if __name__ == [\"']__main__[\"']"),
    ]
    for idx, line in enumerate(lines, start=1):
        if any(pattern.search(line) for pattern in structural_patterns):
            evidence.append(Evidence(path=rel_path, line=idx, text=line.strip()))
        if len(evidence) >= 10:
            break

    if request.profile == Profile.SIMPLE:
        return evidence[:5]
    if request.profile == Profile.STANDARD:
        return evidence[:8]
    return evidence[:12]


def _extract_symbol_block(content: str, symbol: str) -> list[str]:
    if not symbol.strip():
        return []
    lines = content.splitlines()
    def_pattern = re.compile(rf"^(\s*)(def|class)\s+{re.escape(symbol)}\b")
    start_idx = -1
    indent = 0
    for idx, line in enumerate(lines):
        match = def_pattern.search(line)
        if not match:
            continue
        start_idx = idx
        indent = len(match.group(1))
        break
    if start_idx < 0:
        return []
    block: list[str] = []
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if idx > start_idx and line.strip():
            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent <= indent:
                break
        block.append(line)
    return block


def build_behavior_signals(target: ResolvedTarget, request: CommandRequest) -> list[str]:
    source_lines = target.content.splitlines()
    if target.source == "symbol":
        symbol_lines = _extract_symbol_block(target.content, request.payload.strip())
        if symbol_lines:
            source_lines = symbol_lines

    signals: list[str] = []
    seen: set[str] = set()
    for line in source_lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        for signal_id, pattern in BEHAVIOR_SIGNAL_PATTERNS:
            if not pattern.search(stripped):
                continue
            if signal_id == "guard_return" and stripped.endswith(":"):
                rendered = f"{stripped} return ..."
            elif signal_id == "filesystem_mkdir":
                rendered = "creates directories via mkdir(...)"
            elif signal_id == "filesystem_write":
                rendered = "writes file content via write_text(...)"
            elif signal_id == "file_append":
                rendered = "appends to a file via open('a', ...)"
            elif signal_id == "serialization_json":
                rendered = "serializes event payload via json.dumps(...)"
            elif signal_id == "secret_redaction":
                rendered = "redacts sensitive keys before writing"
            else:
                rendered = stripped
            key = rendered.lower()
            if key in seen:
                continue
            seen.add(key)
            signals.append(rendered)
            break
        if len(signals) >= 6:
            break

    if "repo_root / \".forge\" / \"logs\"" in target.content:
        anchor = "targets local log path under .forge/logs"
        if anchor not in signals:
            signals.append(anchor)
    if "llm_observability.jsonl" in target.content.lower():
        anchor = "writes observability events to llm_observability.jsonl"
        if anchor not in signals:
            signals.append(anchor)
    return signals[:8]


def _classify_target_type(
    candidate: Path | None,
    repo_root: Path,
    framework_roots: list[Path],
) -> str:
    if candidate is not None:
        try:
            candidate.relative_to(repo_root)
            return "repo"
        except ValueError:
            pass
        for root in framework_roots:
            try:
                candidate.relative_to(root)
                return "framework"
            except ValueError:
                continue
    return "external"


def _resolve_python_import_target(module: str, rel_target: Path, repo_root: Path) -> Path | None:
    cleaned = module.strip().strip(".")
    if not cleaned:
        return None
    parts = [part for part in cleaned.split(".") if part]
    if not parts:
        return None
    direct = repo_root.joinpath(*parts).with_suffix(".py")
    if direct.exists():
        return direct
    pkg_init = repo_root.joinpath(*parts) / "__init__.py"
    if pkg_init.exists():
        return pkg_init
    relative = (repo_root / rel_target.parent).joinpath(*parts).with_suffix(".py")
    if relative.exists():
        return relative
    return None


def _resolve_literal_target(raw_value: str, rel_target: Path, repo_root: Path) -> Path | None:
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    local = (repo_root / rel_target.parent / candidate).resolve()
    try:
        local.relative_to(repo_root)
    except ValueError:
        return None
    if local.exists():
        return local
    repo_candidate = (repo_root / candidate).resolve()
    try:
        repo_candidate.relative_to(repo_root)
    except ValueError:
        return None
    return repo_candidate if repo_candidate.exists() else None


def _include_by_scope(source_scope: str, target_type: str) -> bool:
    if source_scope == "repo_only":
        return target_type == "repo"
    if source_scope == "framework_only":
        return target_type == "framework"
    return target_type in {"repo", "framework", "external"}


def extract_dependency_edges_out(
    *,
    rel_target: Path,
    content: str,
    repo_root: Path,
    source_scope: str,
    framework_id: str | None,
    framework_version: str | None,
    framework_roots: list[Path],
) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[str, str, int]] = set()
    for idx, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        patterns = [
            (re.match(r"^import\s+([A-Za-z0-9_\.]+)", stripped), "import"),
            (re.match(r"^from\s+([A-Za-z0-9_\.]+)\s+import\s+", stripped), "import_from"),
            (re.search(r"(?:require|import)\(\s*['\"]([^'\"]+)['\"]\s*\)", stripped), "require"),
        ]
        for match, kind in patterns:
            if match is None:
                continue
            raw_target = match.group(1).strip()
            resolved = _resolve_python_import_target(raw_target, rel_target, repo_root)
            if resolved is None:
                resolved = _resolve_literal_target(raw_target, rel_target, repo_root)
            target_type = _classify_target_type(resolved, repo_root, framework_roots)
            if not _include_by_scope(source_scope, target_type):
                break
            marker = (kind, raw_target, idx)
            if marker in seen:
                break
            seen.add(marker)
            target_path = None
            if resolved is not None:
                try:
                    target_path = str(resolved.relative_to(repo_root))
                except ValueError:
                    target_path = str(resolved)
            edges.append(
                Edge(
                    source_path=str(rel_target),
                    target_path=target_path,
                    target_raw=None if target_path else raw_target,
                    edge_kind=kind,
                    evidence=Evidence(path=rel_target, line=idx, text=stripped),
                    confidence="high" if target_path else "medium",
                    source_type="repo",
                    target_type=target_type,
                    framework_id=framework_id if target_type == "framework" else None,
                    framework_version=framework_version if target_type == "framework" else None,
                )
            )
            break
        if len(edges) >= 40:
            break
    return edges[:24]


def extract_dependency_edges_in(
    *,
    rel_target: Path,
    target: ResolvedTarget,
    request: CommandRequest,
    repo_root: Path,
    session: ExecutionSession,
    source_scope: str,
    framework_roots: list[Path],
) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[str, int, str]] = set()
    code_ext = {".py", ".js", ".jsx", ".ts", ".tsx", ".php"}
    rel_target_str = str(rel_target)
    target_stem = rel_target.stem
    symbol = request.payload.strip() if target.source == "symbol" else ""
    probes = [target_stem, rel_target_str]
    if symbol:
        probes.append(symbol)
    for path in iter_repo_files(repo_root, session):
        rel_path = path.relative_to(repo_root)
        if rel_path == rel_target:
            continue
        if rel_path.suffix.lower() not in code_ext:
            continue
        text = read_text_file(path, session)
        if not text:
            continue
        for idx, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            if not any(probe and probe in stripped for probe in probes):
                continue
            lowered = stripped.lower()
            if "import " not in lowered and "from " not in lowered and "require(" not in lowered and "use " not in lowered:
                continue
            target_type = _classify_target_type(path, repo_root, framework_roots)
            if not _include_by_scope(source_scope, target_type):
                continue
            marker = (str(rel_path), idx, stripped)
            if marker in seen:
                continue
            seen.add(marker)
            edges.append(
                Edge(
                    source_path=str(rel_path),
                    target_path=rel_target_str,
                    target_raw=None,
                    edge_kind="reference",
                    evidence=Evidence(path=rel_path, line=idx, text=stripped),
                    confidence="medium",
                    source_type="repo",
                    target_type="repo",
                )
            )
            if len(edges) >= 24:
                return edges
    return edges


def extract_resource_edges(
    *,
    rel_target: Path,
    content: str,
    repo_root: Path,
    source_scope: str,
    framework_id: str | None,
    framework_version: str | None,
    framework_roots: list[Path],
) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[str, str, int]] = set()
    literal_re = re.compile(r"['\"]([^'\"]+\.(?:json|jsonl|toml|yaml|yml|txt|md|j2|jinja|prompt|cfg|ini))['\"]")
    for idx, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        for match in literal_re.finditer(stripped):
            raw_target = match.group(1)
            resolved = _resolve_literal_target(raw_target, rel_target, repo_root)
            target_type = _classify_target_type(resolved, repo_root, framework_roots)
            if not _include_by_scope(source_scope, target_type):
                continue
            if "write" in stripped:
                kind = "file_write"
            elif "read" in stripped or "open(" in stripped:
                kind = "file_read"
            else:
                kind = "resource_ref"
            marker = (kind, raw_target, idx)
            if marker in seen:
                continue
            seen.add(marker)
            target_path = None
            if resolved is not None:
                try:
                    target_path = str(resolved.relative_to(repo_root))
                except ValueError:
                    target_path = str(resolved)
            edges.append(
                Edge(
                    source_path=str(rel_target),
                    target_path=target_path,
                    target_raw=None if target_path else raw_target,
                    edge_kind=kind,
                    evidence=Evidence(path=rel_target, line=idx, text=stripped),
                    confidence="high" if target_path else "medium",
                    source_type="repo",
                    target_type=target_type,
                    framework_id=framework_id if target_type == "framework" else None,
                    framework_version=framework_version if target_type == "framework" else None,
                )
            )
            if len(edges) >= 24:
                return edges
    return edges


def _graph_node_maps(graph: dict[str, object]) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    nodes_raw = graph.get("nodes")
    edges_raw = graph.get("edges")
    node_map: dict[str, dict[str, object]] = {}
    if isinstance(nodes_raw, list):
        for item in nodes_raw:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                node_map[str(item["id"])] = item
    edge_list = [item for item in edges_raw if isinstance(item, dict)] if isinstance(edges_raw, list) else []
    return node_map, edge_list


def _path_from_node(node: dict[str, object]) -> str | None:
    path = node.get("path")
    if isinstance(path, str) and path.strip():
        return path
    return None


def extract_edges_from_graph(
    *,
    graph: dict[str, object],
    rel_target: Path,
    kinds: set[str],
    direction: str,
    source_scope: str,
    framework_ref: str | None = None,
) -> list[Edge]:
    node_map, edges = _graph_node_maps(graph)
    target_file_id = f"file:{rel_target}"
    out: list[Edge] = []
    for edge in edges:
        kind = edge.get("kind")
        if not isinstance(kind, str) or kind not in kinds:
            continue
        source_id = edge.get("source")
        target_id = edge.get("target")
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            continue
        if direction == "out" and source_id != target_file_id:
            continue
        if direction == "in" and target_id != target_file_id:
            continue
        src_node = node_map.get(source_id, {})
        tgt_node = node_map.get(target_id, {})
        source_type = str(edge.get("source_type") or src_node.get("source_type") or "repo")
        target_type = str(tgt_node.get("source_type") or "external")
        if source_scope == "repo_only" and (source_type != "repo" and target_type != "repo"):
            continue
        if source_scope == "framework_only" and target_type != "framework":
            continue
        source_path = _path_from_node(src_node) or str(rel_target)
        target_path = _path_from_node(tgt_node)
        target_raw = None if target_path else (tgt_node.get("package") if isinstance(tgt_node.get("package"), str) else target_id)
        evidence_payload = edge.get("evidence")
        line = 0
        text = f"graph edge: {kind}"
        if isinstance(evidence_payload, list) and evidence_payload:
            first = evidence_payload[0]
            if isinstance(first, dict):
                line = int(first.get("line", 0)) if str(first.get("line", "0")).isdigit() else 0
                raw_text = first.get("text")
                text = str(raw_text) if isinstance(raw_text, str) and raw_text.strip() else text
        framework_id = None
        framework_version = None
        if framework_ref:
            framework_id = framework_ref.split("@", 1)[0]
            framework_version = framework_ref.split("@", 1)[1] if "@" in framework_ref else None
        out.append(
            Edge(
                source_path=source_path,
                target_path=target_path,
                target_raw=target_raw,
                edge_kind=kind,
                evidence=Evidence(path=Path(source_path), line=line, text=text),
                confidence=str(edge.get("confidence") or "medium"),
                source_type=source_type,
                target_type=target_type,
                framework_id=framework_id,
                framework_version=framework_version,
            )
        )
    return out[:24]


def build_focus_answer(
    *,
    focus: str,
    rel_target: Path,
    settings_influences: list[SettingsInfluence],
    default_values: list[DefaultValueSignal],
    llm_participation: list[LLMParticipation],
    output_surfaces: list[OutputSurface],
    symbol_facts: list[SymbolFact],
    dependency_edges_out: list[Edge],
    dependency_edges_in: list[Edge],
    resource_edges: list[Edge],
    direction: str,
    source_scope: str,
) -> str | None:
    if focus == "symbols":
        if not symbol_facts:
            return f"No top-level symbol declarations were detected for {rel_target}."
        return f"{rel_target} exposes {len(symbol_facts)} detected top-level symbols."
    if focus == "dependencies":
        active = dependency_edges_in if direction == "in" else dependency_edges_out
        if not active:
            return (
                f"No {direction}-direction dependency edges were detected for {rel_target} "
                f"within source scope '{source_scope}'."
            )
        return (
            f"{rel_target} has {len(active)} dependency edges in direction '{direction}' "
            f"within source scope '{source_scope}'."
        )
    if focus == "resources":
        if not resource_edges:
            return f"No resource edges were detected for {rel_target} within source scope '{source_scope}'."
        return f"{rel_target} has {len(resource_edges)} resource edges within source scope '{source_scope}'."
    if focus == "uses":
        if not dependency_edges_in:
            return f"No inbound usage edges were detected for {rel_target} within source scope '{source_scope}'."
        return f"{rel_target} is referenced by {len(dependency_edges_in)} inbound usage edges."
    if focus == "settings":
        if not settings_influences:
            return f"No clear settings inputs were detected for {rel_target} in the current static read."
        channels = sorted({item.input_channel for item in settings_influences})
        return (
            f"{rel_target} is influenced by {len(settings_influences)} detected settings inputs "
            f"across channels: {', '.join(channels)}."
        )
    if focus == "defaults":
        if not default_values:
            return f"No explicit in-code default values were detected for {rel_target} in the current static read."
        high_count = sum(1 for item in default_values if item.confidence == "high")
        confidence = confidence_for_hits(high_count)
        return (
            f"{rel_target} defines {len(default_values)} detected default values/signals; "
            f"overall default-detection confidence is {confidence}."
        )
    if focus == "llm":
        if not llm_participation:
            return f"No explicit LLM participation markers were detected for {rel_target}."
        kinds = sorted({item.kind for item in llm_participation})
        return (
            f"{rel_target} shows {len(llm_participation)} LLM participation stages "
            f"with kinds: {', '.join(kinds)}."
        )
    if focus == "outputs":
        if not output_surfaces:
            return f"No explicit output surfaces were detected for {rel_target}."
        surfaces = sorted({item.surface for item in output_surfaces})
        return (
            f"{rel_target} exposes {len(output_surfaces)} output surfaces across: "
            f"{', '.join(surfaces)}."
        )
    return None


def build_deterministic_summary(
    *,
    rel_target: Path,
    role: str,
    target: ResolvedTarget,
    request: CommandRequest,
    behavior_signals: list[str],
) -> str:
    if target.source == "symbol":
        symbol = request.payload.strip()
        if behavior_signals:
            joined = "; ".join(behavior_signals[:4])
            return f"{rel_target} defines {symbol} and appears to: {joined}."
        return f"{rel_target} defines {symbol} and is primarily {role}."
    if behavior_signals:
        joined = "; ".join(behavior_signals[:3])
        return f"{rel_target} is primarily {role} and appears to: {joined}."
    return f"{rel_target} is primarily {role}."


def uncertainty_notes(target: ResolvedTarget, evidence: list[Evidence], profile: Profile) -> list[str]:
    notes: list[str] = []
    if target.source == "symbol":
        notes.append("target was resolved via best-effort symbol matching across files")
    if len(evidence) < 3:
        notes.append("limited structural evidence found in target")
    if profile == Profile.SIMPLE:
        notes.append("simple profile uses target-local analysis only")
    return notes


def build_evidence_facts(repo_root: Path, evidence: list[Evidence]) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for idx, item in enumerate(evidence, start=1):
        fact_id = f"E{idx}"
        rel_path = item.path.relative_to(repo_root)
        facts.append(
            {
                "id": fact_id,
                "path": str(rel_path),
                "line": item.line,
                "fact": item.text,
            }
        )
    return facts


def build_inference_points(
    *,
    role: str,
    rationale: str,
    evidence_facts: list[dict[str, object]],
    profile: Profile,
) -> list[InferencePoint]:
    evidence_ids = [str(item.get("id")) for item in evidence_facts if isinstance(item.get("id"), str)]
    strong = len(evidence_ids) >= 6
    medium = len(evidence_ids) >= 3
    if strong:
        level = "high"
        confidence_reason = "multiple structural evidence anchors are present"
    elif medium:
        level = "medium"
        confidence_reason = "some evidence anchors are present, but coverage is limited"
    else:
        level = "low"
        confidence_reason = "few direct evidence anchors were found"

    points: list[InferencePoint] = [
        InferencePoint(
            inference_id="I1",
            inference=f"Primary role hypothesis: this target is {role}.",
            evidence_ids=evidence_ids[:6],
            rationale=rationale,
            confidence=level,
        )
    ]
    if profile in {Profile.STANDARD, Profile.DETAILED}:
        points.append(
            InferencePoint(
                inference_id="I2",
                inference="The current role classification is based on visible structural markers, not runtime behavior.",
                evidence_ids=evidence_ids[:4],
                rationale="classification uses path/content/index signals from the resolved target",
                confidence="medium" if evidence_ids else "low",
            )
        )
    if profile == Profile.DETAILED:
        points.append(
            InferencePoint(
                inference_id="I3",
                inference="Related-file context may adjust interpretation boundaries for this target.",
                evidence_ids=evidence_ids[:3],
                rationale="related files are detected via deterministic repo-local matching",
                confidence="medium" if len(evidence_ids) >= 3 else "low",
            )
        )
    # Keep rationale from evidence-density computation visible by appending to first point.
    points[0].rationale = f"{points[0].rationale}; {confidence_reason}"
    return points


def build_role_hypothesis_alternatives(
    *,
    role: str,
    profile: Profile,
    evidence_facts: list[dict[str, object]],
) -> list[dict[str, object]]:
    if profile != Profile.DETAILED:
        return []
    evidence_density = len(evidence_facts)
    alternatives: list[dict[str, object]] = []
    if role != "implementation":
        alternatives.append(
            {
                "role": "implementation",
                "rationale": "target may still contain executable/source logic despite current primary role",
                "confidence": "medium" if evidence_density >= 5 else "low",
            }
        )
    if role != "support code":
        alternatives.append(
            {
                "role": "support code",
                "rationale": "helper/utility markers can overlap with implementation structure",
                "confidence": "low",
            }
        )
    return alternatives[:3]


def print_explanation(
    request: CommandRequest,
    repo_root: Path,
    target: ResolvedTarget,
    role: str,
    rationale: str,
    summary: str,
    evidence: list[Evidence],
    related: list[Path],
    uncertainties: list[str],
    index_status: str | None,
    next_step: str,
    view: str,
    inference_points: list[InferencePoint],
    behavior_signals: list[str],
    focus_answer: str | None,
    settings_influences: list[SettingsInfluence],
    default_values: list[DefaultValueSignal],
    explain_focus: str,
    llm_participation: list[LLMParticipation],
    output_surfaces: list[OutputSurface],
    symbol_facts: list[SymbolFact],
    dependency_edges_out: list[Edge],
    dependency_edges_in: list[Edge],
    resource_edges: list[Edge],
    explain_direction: str,
    explain_source_scope: str,
) -> None:
    def _display_path(path: Path) -> Path:
        try:
            return path.relative_to(repo_root)
        except ValueError:
            return path

    rel_target = target.path.relative_to(repo_root)
    print("=== FORGE EXPLAIN ===")
    print(f"Profile: {request.profile.value}")
    print(f"Target: {request.payload}")
    if index_status:
        print(f"Index: {index_status}")
    print(f"Resolved target: {rel_target} ({target.source})")

    print("\n--- Summary ---")
    print(summary)

    if is_full(view):
        print("\n--- Role Classification ---")
        print(f"Role: {role}")
        print(f"Reason: {rationale}")

    print("\n--- Evidence ---")
    if not evidence:
        print("No concrete evidence extracted.")
    evidence_limit = 2 if is_compact(view) else 3 if view == "standard" else len(evidence)
    for item in evidence[:evidence_limit]:
        path_display = _display_path(item.path)
        print(f"{path_display}:{item.line}: {item.text}")

    if is_full(view):
        print("\n--- Behavior Signals ---")
        if behavior_signals:
            for item in behavior_signals:
                print(f"- {item}")
        else:
            print("No clear behavior signals extracted from current target window.")

    if focus_answer:
        print("\n--- Focus Answer ---")
        print(focus_answer)
        if is_full(view):
            if explain_focus == "settings":
                print("\n--- Settings Influences ---")
                if settings_influences:
                    for item in settings_influences[:20]:
                        print(
                            f"- {item.setting_key} [{item.input_channel}] "
                            f"confidence={item.confidence} "
                            f"@ {_display_path(item.evidence.path)}:{item.evidence.line}"
                        )
                        print(f"  {item.effect_summary}")
                else:
                    print("No settings influences detected.")
            if explain_focus == "defaults":
                print("\n--- Default Values ---")
                if default_values:
                    for item in default_values[:20]:
                        print(
                            f"- {item.name}={item.value_repr} "
                            f"confidence={item.confidence} "
                            f"@ {_display_path(item.evidence.path)}:{item.evidence.line}"
                        )
                        print(f"  activation: {item.activation_condition}")
                else:
                    print("No default values detected.")
            if explain_focus == "llm":
                print("\n--- LLM Participation ---")
                if llm_participation:
                    for item in llm_participation[:20]:
                        print(
                            f"- {item.stage} kind={item.kind} confidence={item.confidence} "
                            f"@ {_display_path(item.evidence.path)}:{item.evidence.line}"
                        )
                else:
                    print("No LLM participation markers detected.")
            if explain_focus == "outputs":
                print("\n--- Output Surfaces ---")
                if output_surfaces:
                    for item in output_surfaces[:20]:
                        print(
                            f"- {item.surface} [{item.path_or_section}] producer={item.producer} "
                            f"confidence={item.confidence} "
                            f"@ {_display_path(item.evidence.path)}:{item.evidence.line}"
                        )
                else:
                    print("No output surfaces detected.")
            if explain_focus == "symbols":
                print("\n--- Symbols ---")
                if symbol_facts:
                    for item in symbol_facts[:24]:
                        print(
                            f"- {item.kind} {item.name} confidence={item.confidence} "
                            f"@ {_display_path(item.evidence.path)}:{item.evidence.line}"
                        )
                else:
                    print("No symbols detected.")
            if explain_focus in {"dependencies", "uses"}:
                print("\n--- Dependency Edges Out ---")
                if dependency_edges_out:
                    for item in dependency_edges_out[:24]:
                        target = item.target_path or item.target_raw or "unknown"
                        print(
                            f"- {item.source_path} -> {target} [{item.edge_kind}] "
                            f"type={item.target_type} confidence={item.confidence}"
                        )
                else:
                    print("No outbound dependency edges detected.")
                print("\n--- Dependency Edges In ---")
                if dependency_edges_in:
                    for item in dependency_edges_in[:24]:
                        target = item.target_path or item.target_raw or "unknown"
                        print(
                            f"- {item.source_path} -> {target} [{item.edge_kind}] "
                            f"type={item.target_type} confidence={item.confidence}"
                        )
                else:
                    print("No inbound dependency edges detected.")
            if explain_focus == "resources":
                print("\n--- Resource Edges ---")
                if resource_edges:
                    for item in resource_edges[:24]:
                        target = item.target_path or item.target_raw or "unknown"
                        print(
                            f"- {item.source_path} -> {target} [{item.edge_kind}] "
                            f"type={item.target_type} confidence={item.confidence}"
                        )
                else:
                    print("No resource edges detected.")

    print("\n--- Inference ---")
    inference_limit = 1 if is_compact(view) else 2 if view == "standard" else len(inference_points)
    for point in inference_points[:inference_limit]:
        print(f"- {point.inference}")
        if is_full(view):
            print(f"  rationale: {point.rationale}")

    print("\n--- Confidence ---")
    confidence_limit = 1 if is_compact(view) else 2 if view == "standard" else len(inference_points)
    for point in inference_points[:confidence_limit]:
        print(f"- {point.inference_id}: {point.confidence}")
        if is_full(view):
            print(f"  rationale: {point.rationale}")

    if request.profile in {Profile.STANDARD, Profile.DETAILED} and is_full(view):
        print("\n--- Related Files ---")
        if related:
            related_limit = len(related)
            for rel in related[:related_limit]:
                print(rel)
        else:
            print("No related files found.")

    print("\n--- Uncertainty ---")
    if uncertainties:
        notes = uncertainties if is_full(view) else uncertainties[:1]
        for note in notes:
            print(f"- {note}")
    else:
        print("No major uncertainty flags from current read pass.")

    print("\n--- Next Step ---")
    print(next_step)
    if is_full(view):
        print(f"(focus={explain_focus}, direction={explain_direction}, source_scope={explain_source_scope})")


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    view = resolve_view(args)
    repo_root = Path(args.repo_root).resolve()
    explain_focus = str(getattr(args, "explain_focus", "overview") or "overview")
    explain_focus_source = str(getattr(args, "explain_focus_source", "default") or "default")
    explain_direction_requested = str(getattr(args, "direction", "out") or "out")
    explain_direction = explain_direction_requested
    explain_source_scope = str(getattr(args, "source_scope", "repo_only") or "repo_only")
    explain_command = str(getattr(args, "explain_command", "explain") or "explain")
    try:
        resolved_payload, from_run_meta = resolve_from_run_payload(
            repo_root=repo_root,
            requested_capability=request.capability,
            explicit_payload=request.payload,
            from_run_id=getattr(args, "from_run", None),
            confirm_transition=bool(getattr(args, "confirm_transition", False)),
        )
    except RunReferenceError as exc:
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary="Run reference could not be resolved.",
            evidence=[],
            uncertainty=[str(exc)],
            next_step="Run: forge runs list",
            sections={"status": "from_run_resolution_failed"},
        )
        if args.output_format == "json":
            emit_contract_json(contract)
            return 1
        print(f"Run reference error: {exc}")
        return 1

    request = CommandRequest(capability=request.capability, profile=request.profile, payload=resolved_payload)
    raw_target = request.payload.strip()
    orchestration_catalog = [
        "resolve_target",
        "collect_evidence",
        "extract_facet",
        "synthesize",
        "summarize",
        "finalize",
    ]
    orchestration_actions: list[dict[str, object]] = []

    def mark_action(name: str, status: str, detail: str) -> None:
        orchestration_actions.append({"action": name, "status": status, "detail": detail})

    target = resolve_file_or_symbol_target(repo_root, raw_target, session)

    if target is None:
        mark_action("resolve_target", "failed", "target could not be resolved")
        summary = "Target could not be resolved to a readable file or known symbol."
        uncertainty = [
            "no matching file path under repo root",
            "no symbol-like match found in readable text files",
        ]
        next_step = 'Run: forge query "where is this symbol defined?"'
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=[],
            uncertainty=uncertainty,
            next_step=next_step,
            sections={
                "role_classification": None,
                "related_files": [],
                "related_target_rationale": [],
                "action_orchestration": {
                    "catalog": orchestration_catalog,
                    "iterations": [{"iteration": 1, "actions": orchestration_actions}],
                    "done_reason": "unresolved_target",
                    "usage": {
                        "engine": "core.mode_orchestrator.iter_bounded_cycles",
                        "max_iterations": 1,
                        "max_wall_time_ms": 1200,
                    },
                },
            },
        )
        if args.output_format == "json":
            emit_contract_json(contract)
            return 0
        print("=== FORGE EXPLAIN ===")
        print(f"Profile: {request.profile.value}")
        print(f"Target: {request.payload}")
        print("\n--- Summary ---")
        print(summary)
        print("\n--- Uncertainty ---")
        for note in uncertainty:
            print(f"- {note}")
        print("\n--- Next Step ---")
        print(next_step)
        return 0

    mark_action("resolve_target", "completed", f"resolved to {target.path.relative_to(repo_root)} ({target.source})")
    rel_target = target.path.relative_to(repo_root)
    evidence_limit, evidence_limit_source = _resolve_runtime_int(
        args,
        "explain.evidence.max_items",
        12,
        min_value=1,
        max_value=200,
    )
    edges_limit, edges_limit_source = _resolve_runtime_int(
        args,
        "explain.edges.max_items",
        24,
        min_value=1,
        max_value=200,
    )
    settings_limit, settings_limit_source = _resolve_runtime_int(
        args,
        "explain.settings.max_items",
        20,
        min_value=1,
        max_value=200,
    )
    defaults_limit, defaults_limit_source = _resolve_runtime_int(
        args,
        "explain.defaults.max_items",
        24,
        min_value=1,
        max_value=200,
    )
    outputs_limit, outputs_limit_source = _resolve_runtime_int(
        args,
        "explain.outputs.max_items",
        20,
        min_value=1,
        max_value=200,
    )
    symbols_limit, symbols_limit_source = _resolve_runtime_int(
        args,
        "explain.symbols.max_items",
        24,
        min_value=1,
        max_value=200,
    )
    index_entries = {}
    path_classes: dict[str, str] = {}
    index_status: str | None = None
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        index_entries = load_index_entry_map(repo_root, session)
        path_classes = load_index_path_class_map(repo_root, session)
        if path_classes:
            index_status = "loaded .forge/index.json"
        else:
            index_status = "not available, using direct repository scan only"
    index_entry = index_entries.get(str(rel_target))

    role, rationale = classify_role(rel_target, target.content, index_entry)
    evidence = gather_evidence_for_target(target, request)[:evidence_limit]
    mark_action("collect_evidence", "completed", f"collected {len(evidence)} evidence entries")
    related: list[Path] = []
    related_target_rationale: list[dict[str, object]] = []
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        for cycle in iter_bounded_cycles(max_iterations=1, max_wall_time_ms=800):
            if cycle.wall_time_exhausted:
                break
            ranked_related = rank_related_targets(repo_root, rel_target, session, path_classes, limit=10)
            related_abs = [repo_root / item.path for item in ranked_related]
            prioritized = prioritize_paths_by_index(
                repo_root,
                related_abs,
                path_classes,
                exclude_non_index_participating=True,
            )
            if not prioritized:
                prioritized = related_abs
            related = [path.relative_to(repo_root) for path in prioritized[:5]]
            ranked_map = {item.path: item for item in ranked_related}
            selected_ranked: list[RelatedTarget] = []
            for rel in related:
                ranked = ranked_map.get(rel)
                if ranked is not None:
                    selected_ranked.append(ranked)
            related_target_rationale = [
                {"path": str(item.path), "score": item.score, "rationale": item.rationale}
                for item in selected_ranked
            ]
            break
    uncertainties = uncertainty_notes(target, evidence, request.profile)
    if explain_focus == "uses" and explain_direction_requested != "in":
        explain_direction = "in"
        uncertainties.append(
            f"explain uses semantics: direction '{explain_direction_requested}' is normalized to 'in'."
        )
    next_step = f"Run: forge review {rel_target}"
    evidence_payload = [
        {
            "path": str(item.path.relative_to(repo_root)),
            "line": item.line,
            "text": item.text,
            "source_type": "repo",
            "source_origin": "repo",
            "framework_id": None,
            "framework_version": None,
        }
        for item in evidence
    ]
    evidence_facts = build_evidence_facts(repo_root, evidence)
    behavior_signals = build_behavior_signals(target, request)
    repo_graph = load_repo_graph(repo_root, session)
    framework_graphs, framework_graph_warnings = load_framework_graph_references(repo_root, session)
    if framework_graph_warnings and is_full(view):
        uncertainties.extend(framework_graph_warnings[:3])
    framework_roots: list[Path] = []
    framework_id: str | None = None
    framework_version: str | None = None
    if explain_source_scope in {"framework_only", "all"}:
        registry = load_framework_registry(repo_root, session)
        profile, _, warnings = select_framework_profile(registry, None)
        if profile is not None:
            framework_roots = [*profile.framework_roots, *profile.framework_docs_roots]
            framework_id = profile.profile_id
            framework_version = profile.version
        elif explain_source_scope == "framework_only":
            uncertainties.append("source_scope=framework_only but no framework profile/roots are configured")
        if warnings and is_full(view):
            uncertainties.extend(warnings[:3])

    symbol_facts = extract_symbol_facts(rel_target, target.content)[:symbols_limit] if explain_focus == "symbols" else []
    dependency_edges_out: list[Edge] = []
    dependency_edges_in: list[Edge] = []
    resource_edges: list[Edge] = []
    if explain_focus in {"dependencies", "uses", "resources"}:
        if repo_graph is not None:
            if explain_focus == "dependencies":
                dependency_edges_out.extend(
                    extract_edges_from_graph(
                        graph=repo_graph,
                        rel_target=rel_target,
                        kinds={"import", "call", "symbol_ref"},
                        direction="out",
                        source_scope=explain_source_scope,
                    )
                )
            if explain_focus in {"dependencies", "uses"}:
                dependency_edges_in.extend(
                    extract_edges_from_graph(
                        graph=repo_graph,
                        rel_target=rel_target,
                        kinds={"import", "call", "symbol_ref"},
                        direction="in",
                        source_scope=explain_source_scope,
                    )
                )
            if explain_focus == "resources":
                resource_edges.extend(
                    extract_edges_from_graph(
                        graph=repo_graph,
                        rel_target=rel_target,
                        kinds={"resource_read", "resource_write"},
                        direction="out",
                        source_scope=explain_source_scope,
                    )
                )
        if explain_source_scope in {"framework_only", "all"} and framework_graphs:
            for ref_id, graph in framework_graphs.items():
                if explain_focus == "dependencies":
                    dependency_edges_out.extend(
                        extract_edges_from_graph(
                            graph=graph,
                            rel_target=rel_target,
                            kinds={"import", "call", "symbol_ref"},
                            direction="out",
                            source_scope=explain_source_scope,
                            framework_ref=ref_id,
                        )
                    )
                if explain_focus in {"dependencies", "uses"}:
                    dependency_edges_in.extend(
                        extract_edges_from_graph(
                            graph=graph,
                            rel_target=rel_target,
                            kinds={"import", "call", "symbol_ref"},
                            direction="in",
                            source_scope=explain_source_scope,
                            framework_ref=ref_id,
                        )
                    )
                if explain_focus == "resources":
                    resource_edges.extend(
                        extract_edges_from_graph(
                            graph=graph,
                            rel_target=rel_target,
                            kinds={"resource_read", "resource_write"},
                            direction="out",
                            source_scope=explain_source_scope,
                            framework_ref=ref_id,
                        )
                    )
        # Deterministic fallback when graph data is missing or provides no target edges.
        if explain_focus == "dependencies" and not dependency_edges_out:
            dependency_edges_out = extract_dependency_edges_out(
                rel_target=rel_target,
                content=target.content,
                repo_root=repo_root,
                source_scope=explain_source_scope,
                framework_id=framework_id,
                framework_version=framework_version,
                framework_roots=framework_roots,
            )
        if explain_focus in {"dependencies", "uses"} and not dependency_edges_in:
            dependency_edges_in = extract_dependency_edges_in(
                rel_target=rel_target,
                target=target,
                request=request,
                repo_root=repo_root,
                session=session,
                source_scope=explain_source_scope,
                framework_roots=framework_roots,
            )
        if explain_focus == "resources" and not resource_edges:
            resource_edges = extract_resource_edges(
                rel_target=rel_target,
                content=target.content,
                repo_root=repo_root,
                source_scope=explain_source_scope,
                framework_id=framework_id,
                framework_version=framework_version,
                framework_roots=framework_roots,
            )
        if explain_source_scope in {"framework_only", "all"} and not framework_graphs and explain_source_scope == "framework_only":
            uncertainties.append("no framework graph refs configured; graph scope degraded")
    dependency_edges_out = dependency_edges_out[:edges_limit]
    dependency_edges_in = dependency_edges_in[:edges_limit]
    resource_edges = resource_edges[:edges_limit]
    settings_influences = (
        extract_settings_influences(rel_target, target.content)[:settings_limit] if explain_focus == "settings" else []
    )
    default_values = extract_default_values(rel_target, target.content)[:defaults_limit] if explain_focus == "defaults" else []
    llm_participation = extract_llm_participation(rel_target, target.content)[:settings_limit] if explain_focus == "llm" else []
    output_surfaces = extract_output_surfaces(rel_target, target.content)[:outputs_limit] if explain_focus == "outputs" else []
    mark_action("extract_facet", "completed", f"focus={explain_focus}")
    focus_answer = build_focus_answer(
        focus=explain_focus,
        rel_target=rel_target,
        settings_influences=settings_influences,
        default_values=default_values,
        llm_participation=llm_participation,
        output_surfaces=output_surfaces,
        symbol_facts=symbol_facts,
        dependency_edges_out=dependency_edges_out,
        dependency_edges_in=dependency_edges_in,
        resource_edges=resource_edges,
        direction=explain_direction,
        source_scope=explain_source_scope,
    )
    inference_points = build_inference_points(
        role=role,
        rationale=rationale,
        evidence_facts=evidence_facts,
        profile=request.profile,
    )
    role_hypothesis_alternatives = build_role_hypothesis_alternatives(
        role=role,
        profile=request.profile,
        evidence_facts=evidence_facts,
    )
    mark_action("synthesize", "completed", "built role/evidence/inference synthesis payload")
    sections = {
        "explain": {
            "command": explain_command,
            "focus": explain_focus,
            "focus_source": explain_focus_source,
            "direction": explain_direction,
            "direction_requested": explain_direction_requested,
            "direction_effective": explain_direction,
            "source_scope": explain_source_scope,
        },
        "explain_limits": {
            "values": {
                "evidence_max_items": evidence_limit,
                "edges_max_items": edges_limit,
                "settings_max_items": settings_limit,
                "defaults_max_items": defaults_limit,
                "outputs_max_items": outputs_limit,
                "symbols_max_items": symbols_limit,
            },
            "sources": {
                "evidence_max_items": evidence_limit_source,
                "edges_max_items": edges_limit_source,
                "settings_max_items": settings_limit_source,
                "defaults_max_items": defaults_limit_source,
                "outputs_max_items": outputs_limit_source,
                "symbols_max_items": symbols_limit_source,
            },
        },
        "graph_usage": {
            "repo_graph_loaded": repo_graph is not None,
            "framework_graph_refs_loaded": sorted(framework_graphs.keys()),
        },
        "role_classification": {"role": role, "reason": rationale},
        "related_files": [str(path) for path in related],
        "related_target_rationale": related_target_rationale,
        "resolved_target": str(rel_target),
        "resolved_target_source": {
            "source_type": "repo",
            "source_origin": "repo",
            "framework_id": None,
            "framework_version": None,
        },
        "evidence_facts": evidence_facts,
        "inference_points": [
            {
                "id": point.inference_id,
                "inference": point.inference,
                "evidence_ids": point.evidence_ids,
                "rationale": point.rationale,
            }
            for point in inference_points
        ],
        "confidence": [
            {
                "inference_id": point.inference_id,
                "level": point.confidence,
                "rationale": point.rationale,
            }
            for point in inference_points
        ],
        "behavior_signals": behavior_signals,
        "action_orchestration": {
            "catalog": orchestration_catalog,
            "iterations": [{"iteration": 1, "actions": orchestration_actions}],
            "done_reason": "completed",
            "usage": {
                "engine": "core.mode_orchestrator.iter_bounded_cycles",
                "max_iterations": 1,
                "max_wall_time_ms": 1200,
            },
        },
    }
    if explain_focus == "settings":
        sections["direct_answer"] = focus_answer
        sections["settings_influences"] = [
            {
                "setting_key": item.setting_key,
                "input_channel": item.input_channel,
                "effect_summary": item.effect_summary,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
            }
            for item in settings_influences
        ]
    if explain_focus == "defaults":
        sections["direct_answer"] = focus_answer
        sections["default_values"] = [
            {
                "name": item.name,
                "value_repr": item.value_repr,
                "activation_condition": item.activation_condition,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
            }
            for item in default_values
        ]
    if explain_focus == "llm":
        sections["direct_answer"] = focus_answer
        sections["llm_participation"] = [
            {
                "stage": item.stage,
                "kind": item.kind,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
            }
            for item in llm_participation
        ]
    if explain_focus == "outputs":
        sections["direct_answer"] = focus_answer
        sections["output_surfaces"] = [
            {
                "surface": item.surface,
                "path_or_section": item.path_or_section,
                "producer": item.producer,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
            }
            for item in output_surfaces
        ]
    if explain_focus == "symbols":
        sections["direct_answer"] = focus_answer
        sections["symbols"] = [
            {
                "name": item.name,
                "kind": item.kind,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
            }
            for item in symbol_facts
        ]
    if explain_focus in {"dependencies", "uses"}:
        sections["direct_answer"] = focus_answer
        sections["dependency_edges_out"] = [
            {
                "source_path": item.source_path,
                "target_path": item.target_path,
                "target_raw": item.target_raw,
                "edge_kind": item.edge_kind,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
                "source_type": item.source_type,
                "target_type": item.target_type,
                "framework_id": item.framework_id,
                "framework_version": item.framework_version,
            }
            for item in dependency_edges_out
        ]
        sections["dependency_edges_in"] = [
            {
                "source_path": item.source_path,
                "target_path": item.target_path,
                "target_raw": item.target_raw,
                "edge_kind": item.edge_kind,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
                "source_type": item.source_type,
                "target_type": item.target_type,
                "framework_id": item.framework_id,
                "framework_version": item.framework_version,
            }
            for item in dependency_edges_in
        ]
    if explain_focus == "resources":
        sections["direct_answer"] = focus_answer
        sections["resource_edges"] = [
            {
                "source_path": item.source_path,
                "target_path": item.target_path,
                "target_raw": item.target_raw,
                "edge_kind": item.edge_kind,
                "evidence": {
                    "path": str(item.evidence.path),
                    "line": item.evidence.line,
                    "text": item.evidence.text,
                },
                "confidence": item.confidence,
                "source_type": item.source_type,
                "target_type": item.target_type,
                "framework_id": item.framework_id,
                "framework_version": item.framework_version,
            }
            for item in resource_edges
        ]
    if role_hypothesis_alternatives:
        sections["role_hypothesis_alternatives"] = role_hypothesis_alternatives
    if from_run_meta:
        sections.update(from_run_meta)
    if focus_answer:
        deterministic_summary = focus_answer
    else:
        deterministic_summary = build_deterministic_summary(
            rel_target=rel_target,
            role=role,
            target=target,
            request=request,
            behavior_signals=behavior_signals,
        )
    llm_settings = resolve_settings(args, repo_root)
    llm_outcome = maybe_refine_summary(
        capability=request.capability,
        profile=request.profile,
        task=request.payload,
        deterministic_summary=deterministic_summary,
        evidence=evidence_payload,
        settings=llm_settings,
        repo_root=repo_root,
    )
    summary = llm_outcome.summary
    mark_action("summarize", "completed", "applied deterministic+llm summary step")
    uncertainties.extend(llm_outcome.uncertainty_notes)
    sections["llm_usage"] = llm_outcome.usage
    sections["provenance"] = provenance_section(
        llm_used=bool(llm_outcome.usage.get("used")),
        evidence_count=len(evidence_payload),
    )
    mark_action("finalize", "completed", "assembled final output contract")

    contract = build_contract(
        capability=request.capability.value,
        profile=request.profile.value,
        summary=summary,
        evidence=evidence_payload,
        uncertainty=uncertainties,
        next_step=next_step,
        sections=sections,
    )
    if args.output_format == "json":
        emit_contract_json(contract)
        return 0

    print_explanation(
        request=request,
        repo_root=repo_root,
        target=target,
        role=role,
        rationale=rationale,
        summary=summary,
        evidence=evidence,
        related=related,
        uncertainties=uncertainties,
        index_status=index_status,
        next_step=next_step,
        view=view,
        inference_points=inference_points,
        behavior_signals=behavior_signals,
        focus_answer=focus_answer,
        settings_influences=settings_influences,
        default_values=default_values,
        explain_focus=explain_focus,
        llm_participation=llm_participation,
        output_surfaces=output_surfaces,
        symbol_facts=symbol_facts,
        dependency_edges_out=dependency_edges_out,
        dependency_edges_in=dependency_edges_in,
        resource_edges=resource_edges,
        explain_direction=explain_direction,
        explain_source_scope=explain_source_scope,
    )
    if is_full(view):
        print("\n--- Explain ---")
        print(f"Command: {explain_command}")
        print(f"Focus: {explain_focus}")
        print(f"Focus source: {explain_focus_source}")
        print(f"Direction: {explain_direction}")
        if explain_direction_requested != explain_direction:
            print(f"Direction requested: {explain_direction_requested}")
        print(f"Source scope: {explain_source_scope}")
        print(
            "Limits: "
            f"evidence={evidence_limit} ({evidence_limit_source}), "
            f"edges={edges_limit} ({edges_limit_source}), "
            f"settings={settings_limit} ({settings_limit_source}), "
            f"defaults={defaults_limit} ({defaults_limit_source}), "
            f"outputs={outputs_limit} ({outputs_limit_source}), "
            f"symbols={symbols_limit} ({symbols_limit_source})"
        )
    if from_run_meta:
        print("\n--- From Run ---")
        print(f"Source run id: {from_run_meta['source_run_id']}")
        print(f"Source capability: {from_run_meta['source_run_capability']}")
        print(f"Strategy: {from_run_meta['resolved_from_run_strategy']}")
        print(f"Resolved payload: {from_run_meta['resolved_from_run_payload']}")
        if "transition_source_mode" in from_run_meta and "transition_target_mode" in from_run_meta:
            print(f"Transition: {from_run_meta['transition_source_mode']} -> {from_run_meta['transition_target_mode']}")
            print(f"Transition policy: {from_run_meta.get('transition_policy_reason', 'n/a')}")
        gate_decisions = from_run_meta.get("transition_gate_decisions", [])
        if is_full(view) and isinstance(gate_decisions, list):
            print("Transition gates:")
            for item in gate_decisions:
                if not isinstance(item, dict):
                    continue
                print(
                    f"- {item.get('gate', '?')}: {item.get('status', '?')} "
                    f"({item.get('detail', 'no detail')})"
                )
    if is_full(view):
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
    return 0
