"""Deterministic repository graph cache helpers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import tomli

from core.capability_model import EffectClass
from core.effects import ExecutionSession

GRAPH_VERSION = 1
SUPPORTED_GRAPH_VERSIONS = {GRAPH_VERSION}

_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".php",
    ".sh",
}

_RESOURCE_SUFFIXES = (
    ".json",
    ".jsonl",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
    ".md",
    ".ini",
    ".cfg",
    ".j2",
    ".jinja",
    ".prompt",
)


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _edge_id(kind: str, source: str, target: str, line: int, detector: str) -> str:
    digest = hashlib.sha1(f"{kind}|{source}|{target}|{line}|{detector}".encode("utf-8")).hexdigest()[:16]
    return f"edge:{digest}"


def _source_id_for_repo(repo_root: Path) -> str:
    return f"repo:{repo_root}"


def _node_id_for_file(path: str) -> str:
    return f"file:{path}"


def _node_id_for_symbol(path: str, symbol: str) -> str:
    return f"symbol:{path}:{symbol}"


def _node_id_for_external(raw: str) -> str:
    return f"external:{raw}"


def load_repo_graph(repo_root: Path, session: ExecutionSession) -> dict[str, object] | None:
    payload, _warnings = load_repo_graph_with_warnings(repo_root, session)
    return payload


def _validate_graph_payload(payload: object, *, label: str) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(payload, dict):
        return None, f"{label}: payload is not an object"
    graph_version = payload.get("graph_version")
    if not isinstance(graph_version, int):
        return None, f"{label}: missing or invalid graph_version"
    if graph_version not in SUPPORTED_GRAPH_VERSIONS:
        supported = ", ".join(str(item) for item in sorted(SUPPORTED_GRAPH_VERSIONS))
        return None, f"{label}: unsupported graph_version={graph_version} (supported: {supported})"
    source_type = payload.get("source_type")
    if not isinstance(source_type, str) or not source_type.strip():
        return None, f"{label}: missing or invalid source_type"
    source_id = payload.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        return None, f"{label}: missing or invalid source_id"
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return None, f"{label}: missing or invalid nodes list"
    edges = payload.get("edges")
    if not isinstance(edges, list):
        return None, f"{label}: missing or invalid edges list"
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        return None, f"{label}: missing or invalid stats object"
    return payload, None


def load_repo_graph_with_warnings(repo_root: Path, session: ExecutionSession) -> tuple[dict[str, object] | None, list[str]]:
    graph_path = repo_root / ".forge" / "graph.json"
    if not graph_path.exists():
        return None, []
    session.record_effect(EffectClass.READ_ONLY, f"read graph cache {graph_path}")
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, [f"repo graph invalid: unreadable graph artifact at {graph_path}"]
    validated, warning = _validate_graph_payload(payload, label=f"repo graph {graph_path}")
    if validated is None:
        return None, [f"repo graph invalid: {warning}"]
    return validated, []


def load_framework_graph_references(
    repo_root: Path,
    session: ExecutionSession,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    config_path = repo_root / ".forge" / "config.toml"
    if not config_path.exists():
        return {}, []
    session.record_effect(EffectClass.READ_ONLY, f"read graph config {config_path}")
    try:
        payload = tomli.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return {}, []
    graph_cfg = payload.get("graph")
    refs = graph_cfg.get("framework_refs") if isinstance(graph_cfg, dict) else None
    if not isinstance(refs, dict):
        return {}, []
    loaded: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    for ref_id, raw in refs.items():
        if not isinstance(ref_id, str) or not isinstance(raw, str):
            continue
        candidate = Path(raw).expanduser()
        graph_path = candidate if candidate.is_absolute() else (repo_root / candidate)
        if not graph_path.exists():
            warnings.append(f"framework graph ref missing: {ref_id} -> {graph_path}")
            continue
        session.record_effect(EffectClass.READ_ONLY, f"read framework graph {graph_path}")
        try:
            graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            warnings.append(f"framework graph ref unreadable: {ref_id} -> {graph_path}")
            continue
        if not isinstance(graph_payload, dict):
            warnings.append(f"framework graph ref invalid payload: {ref_id}")
            continue
        loaded[ref_id] = graph_payload
    return loaded, warnings


def build_repo_graph(
    *,
    repo_root: Path,
    file_entries: list[dict[str, object]],
    session: ExecutionSession,
    existing_graph: dict[str, object] | None = None,
    max_nodes: int = 30000,
    max_edges: int = 120000,
) -> tuple[dict[str, object], list[str]]:
    source_id = _source_id_for_repo(repo_root)
    warnings: list[str] = []

    existing_nodes: dict[str, dict[str, object]] = {}
    existing_edges: dict[str, dict[str, object]] = {}
    existing_by_file: dict[str, dict[str, object]] = {}
    existing_hashes: dict[str, str] = {}
    if isinstance(existing_graph, dict):
        for node in existing_graph.get("nodes", []):
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                existing_nodes[node["id"]] = node
        for edge in existing_graph.get("edges", []):
            if isinstance(edge, dict) and isinstance(edge.get("id"), str):
                existing_edges[edge["id"]] = edge
        by_file = existing_graph.get("by_file")
        if isinstance(by_file, dict):
            existing_by_file = {k: v for k, v in by_file.items() if isinstance(k, str) and isinstance(v, dict)}
        hashes = existing_graph.get("file_hashes")
        if isinstance(hashes, dict):
            for k, v in hashes.items():
                if isinstance(k, str) and isinstance(v, str):
                    existing_hashes[k] = v

    nodes: dict[str, dict[str, object]] = {}
    edges: dict[str, dict[str, object]] = {}
    by_file: dict[str, dict[str, object]] = {}
    file_hashes: dict[str, str] = {}

    reused_files = 0
    rebuilt_files = 0

    repo_file_paths: set[str] = set()
    for entry in file_entries:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if isinstance(rel, str):
            repo_file_paths.add(rel)

    def ensure_node(node: dict[str, object]) -> str:
        node_id = str(node["id"])
        if len(nodes) < max_nodes:
            nodes[node_id] = node
        return node_id

    def add_edge(edge: dict[str, object]) -> str:
        edge_id = str(edge["id"])
        if len(edges) < max_edges:
            edges[edge_id] = edge
        return edge_id

    for entry in file_entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("path")
        if not isinstance(rel_path, str):
            continue
        content_hash = entry.get("content_hash")
        if not isinstance(content_hash, str):
            content_hash = entry.get("hash") if isinstance(entry.get("hash"), str) else ""
        file_hashes[rel_path] = content_hash
        file_node_id = _node_id_for_file(rel_path)
        ensure_node(
            {
                "id": file_node_id,
                "kind": "file",
                "source_type": "repo",
                "source_id": source_id,
                "path": rel_path,
                "framework_id": None,
                "framework_version": None,
                "package": None,
            }
        )

        prev_hash = existing_hashes.get(rel_path)
        prev_refs = existing_by_file.get(rel_path, {})
        if prev_hash == content_hash and isinstance(prev_refs.get("edge_ids"), list):
            reused_files += 1
            edge_ids = [edge_id for edge_id in prev_refs.get("edge_ids", []) if isinstance(edge_id, str)]
            node_ids = [file_node_id]
            for edge_id in edge_ids:
                edge = existing_edges.get(edge_id)
                if edge is None:
                    continue
                add_edge(edge)
                src = edge.get("source")
                tgt = edge.get("target")
                if isinstance(src, str) and src in existing_nodes:
                    ensure_node(existing_nodes[src])
                    node_ids.append(src)
                if isinstance(tgt, str) and tgt in existing_nodes:
                    ensure_node(existing_nodes[tgt])
                    node_ids.append(tgt)
            by_file[rel_path] = {"node_ids": sorted(set(node_ids)), "edge_ids": sorted(set(edge_ids))}
            continue

        rebuilt_files += 1
        path = repo_root / rel_path
        text = _safe_read_text(path)
        if not text:
            by_file[rel_path] = {"node_ids": [file_node_id], "edge_ids": []}
            continue
        if path.suffix.lower() not in _CODE_EXTENSIONS:
            by_file[rel_path] = {"node_ids": [file_node_id], "edge_ids": []}
            continue

        node_ids: set[str] = {file_node_id}
        edge_ids: set[str] = set()
        lines = text.splitlines()

        for idx, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not stripped:
                continue

            m_symbol = re.match(r"^(def|class|function)\s+([A-Za-z_][A-Za-z0-9_]*)\b", stripped)
            if m_symbol:
                symbol_name = m_symbol.group(2)
                symbol_id = _node_id_for_symbol(rel_path, symbol_name)
                ensure_node(
                    {
                        "id": symbol_id,
                        "kind": "symbol",
                        "source_type": "repo",
                        "source_id": source_id,
                        "path": rel_path,
                        "framework_id": None,
                        "framework_version": None,
                        "package": None,
                    }
                )
                node_ids.add(symbol_id)
                edge = {
                    "id": _edge_id("symbol_def", file_node_id, symbol_id, idx, "symbol_scan"),
                    "kind": "symbol_def",
                    "source": file_node_id,
                    "target": symbol_id,
                    "evidence": [{"path": rel_path, "line": idx, "text": stripped}],
                    "confidence": "high",
                    "detector": "symbol_scan",
                    "source_type": "repo",
                    "source_id": source_id,
                }
                edge_ids.add(add_edge(edge))

            import_patterns = [
                (re.match(r"^import\s+([A-Za-z0-9_\.]+)", stripped), "import_scan"),
                (re.match(r"^from\s+([A-Za-z0-9_\.]+)\s+import\s+", stripped), "import_scan"),
                (re.search(r"(?:require|import)\(\s*['\"]([^'\"]+)['\"]\s*\)", stripped), "import_scan"),
            ]
            for match, detector in import_patterns:
                if match is None:
                    continue
                raw_target = match.group(1).strip().strip(".")
                if not raw_target:
                    continue
                parts = [part for part in raw_target.split(".") if part]
                resolved = repo_root.joinpath(*parts).with_suffix(".py") if parts else None
                if resolved is None or not resolved.exists():
                    resolved = (repo_root / raw_target).resolve() if raw_target.startswith((".", "/")) else None
                if resolved is not None and resolved.exists():
                    try:
                        target_rel = str(resolved.relative_to(repo_root))
                    except ValueError:
                        target_rel = None
                else:
                    target_rel = None
                if target_rel is not None:
                    target_id = _node_id_for_file(target_rel)
                    ensure_node(
                        {
                            "id": target_id,
                            "kind": "file",
                            "source_type": "repo",
                            "source_id": source_id,
                            "path": target_rel,
                            "framework_id": None,
                            "framework_version": None,
                            "package": None,
                        }
                    )
                else:
                    target_id = _node_id_for_external(raw_target)
                    ensure_node(
                        {
                            "id": target_id,
                            "kind": "external",
                            "source_type": "external",
                            "source_id": source_id,
                            "path": None,
                            "framework_id": None,
                            "framework_version": None,
                            "package": raw_target,
                        }
                    )
                node_ids.add(target_id)
                edge = {
                    "id": _edge_id("import", file_node_id, target_id, idx, detector),
                    "kind": "import",
                    "source": file_node_id,
                    "target": target_id,
                    "evidence": [{"path": rel_path, "line": idx, "text": stripped}],
                    "confidence": "high" if target_rel is not None else "medium",
                    "detector": detector,
                    "source_type": "repo",
                    "source_id": source_id,
                }
                edge_ids.add(add_edge(edge))
                break

            for lit in re.findall(r"['\"]([^'\"]+)['\"]", stripped):
                lit_lower = lit.lower()
                if not lit_lower.endswith(_RESOURCE_SUFFIXES):
                    continue
                if "/" in lit or "\\" in lit or "." in lit:
                    candidate = (repo_root / rel_path).parent / lit
                else:
                    candidate = repo_root / lit
                candidate = candidate.resolve()
                target_rel: str | None = None
                try:
                    if candidate.exists():
                        target_rel = str(candidate.relative_to(repo_root))
                except ValueError:
                    target_rel = None
                if target_rel is not None:
                    target_id = _node_id_for_file(target_rel)
                    ensure_node(
                        {
                            "id": target_id,
                            "kind": "file",
                            "source_type": "repo",
                            "source_id": source_id,
                            "path": target_rel,
                            "framework_id": None,
                            "framework_version": None,
                            "package": None,
                        }
                    )
                else:
                    target_id = _node_id_for_external(lit)
                    ensure_node(
                        {
                            "id": target_id,
                            "kind": "external",
                            "source_type": "external",
                            "source_id": source_id,
                            "path": None,
                            "framework_id": None,
                            "framework_version": None,
                            "package": lit,
                        }
                    )
                node_ids.add(target_id)
                kind = "resource_write" if any(key in stripped for key in ("write", "dump", "save")) else "resource_read"
                edge = {
                    "id": _edge_id(kind, file_node_id, target_id, idx, "resource_scan"),
                    "kind": kind,
                    "source": file_node_id,
                    "target": target_id,
                    "evidence": [{"path": rel_path, "line": idx, "text": stripped}],
                    "confidence": "high" if target_rel is not None else "medium",
                    "detector": "resource_scan",
                    "source_type": "repo",
                    "source_id": source_id,
                }
                edge_ids.add(add_edge(edge))
                break

            call_hits = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", stripped)
            if call_hits and not stripped.startswith(("def ", "class ")):
                callee = call_hits[0]
                target_id = _node_id_for_external(f"call:{callee}")
                ensure_node(
                    {
                        "id": target_id,
                        "kind": "symbol_ref",
                        "source_type": "repo",
                        "source_id": source_id,
                        "path": rel_path,
                        "framework_id": None,
                        "framework_version": None,
                        "package": None,
                    }
                )
                node_ids.add(target_id)
                call_edge = {
                    "id": _edge_id("call", file_node_id, target_id, idx, "call_scan"),
                    "kind": "call",
                    "source": file_node_id,
                    "target": target_id,
                    "evidence": [{"path": rel_path, "line": idx, "text": stripped}],
                    "confidence": "low",
                    "detector": "call_scan",
                    "source_type": "repo",
                    "source_id": source_id,
                }
                ref_edge = {
                    "id": _edge_id("symbol_ref", file_node_id, target_id, idx, "call_scan"),
                    "kind": "symbol_ref",
                    "source": file_node_id,
                    "target": target_id,
                    "evidence": [{"path": rel_path, "line": idx, "text": stripped}],
                    "confidence": "low",
                    "detector": "call_scan",
                    "source_type": "repo",
                    "source_id": source_id,
                }
                edge_ids.add(add_edge(call_edge))
                edge_ids.add(add_edge(ref_edge))

        by_file[rel_path] = {"node_ids": sorted(node_ids), "edge_ids": sorted(edge_ids)}

    payload = {
        "graph_version": GRAPH_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "source_type": "repo",
        "source_id": source_id,
        "nodes": sorted(nodes.values(), key=lambda item: str(item.get("id", ""))),
        "edges": sorted(edges.values(), key=lambda item: str(item.get("id", ""))),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "reused_files": reused_files,
            "rebuilt_files": rebuilt_files,
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "warnings": warnings[:30],
            "warning_count": len(warnings),
        },
        "file_hashes": file_hashes,
        "by_file": by_file,
    }
    if len(nodes) >= max_nodes:
        warnings.append("graph node cap reached; output truncated")
    if len(edges) >= max_edges:
        warnings.append("graph edge cap reached; output truncated")
    payload["stats"]["warnings"] = warnings[:30]
    payload["stats"]["warning_count"] = len(warnings)
    return payload, warnings
