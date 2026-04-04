from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import tomli
from core.capability_model import CommandRequest, EffectClass
from core.effects import ExecutionSession
from core.graph_cache import build_repo_graph, load_repo_graph_with_warnings
from core.repo_io import write_forge_file


HARD_IGNORE = {
    ".git",
    ".forge",
    "__pycache__",
    ".idea",
    ".venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "htmlcov",
}

INDEX_EXCLUDE = {"vendor"}
LOW_PRIORITY = {"docs", "scripts", "examples"}
PREFERRED = {"src", "tests", "configuration"}
DEFAULT_SUMMARY_VERSION = 1
DEFAULT_MAX_SUMMARY_CHARS = 220


def classify_relative_path(relative: Path) -> tuple[str, str]:
    """Return (path_class, index_participation_state)."""
    lowered_parts = [part.lower() for part in relative.parts]
    if any(part in HARD_IGNORE for part in lowered_parts):
        return "hard_ignore", "excluded"
    if any(part in INDEX_EXCLUDE for part in lowered_parts):
        return "index_exclude", "excluded"
    if any(part in LOW_PRIORITY for part in lowered_parts):
        return "low_priority", "included"
    if any(part in PREFERRED for part in lowered_parts):
        return "preferred", "included"
    return "normal", "included"


def extract_python_symbols(path: Path) -> list[str]:
    symbols: list[str] = []
    if path.suffix.lower() != ".py":
        return symbols
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if line.startswith("def ") or line.startswith("class "):
                name = stripped.split("(", 1)[0].split(":", 1)[0]
                symbols.append(name.replace("def ", "").replace("class ", "").strip())
    except (OSError, UnicodeDecodeError):
        return []
    return symbols[:50]


def optional_file_hash(path: Path) -> str | None:
    try:
        size = path.stat().st_size
        if size > 1_000_000:
            return None
        digest = hashlib.sha1(path.read_bytes()).hexdigest()
        return digest
    except OSError:
        return None


def load_existing_index(repo_root: Path) -> dict[str, object] | None:
    path = repo_root / ".forge" / "index.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _existing_entry_map(existing_index: dict[str, object] | None) -> dict[tuple[str, str], dict[str, object]]:
    if not isinstance(existing_index, dict):
        return {}
    entries = existing_index.get("entries")
    if not isinstance(entries, dict):
        return {}

    mapping: dict[tuple[str, str], dict[str, object]] = {}
    for bucket in ("files", "directories"):
        raw_items = entries.get(bucket)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            path = item.get("path")
            if not isinstance(kind, str) or not isinstance(path, str):
                continue
            mapping[(kind, path)] = item
    return mapping


def load_index_enrichment_config(repo_root: Path) -> tuple[bool, int, int]:
    config_path = repo_root / ".forge" / "config.toml"
    enabled = True
    summary_version = DEFAULT_SUMMARY_VERSION
    max_chars = DEFAULT_MAX_SUMMARY_CHARS
    if not config_path.exists():
        return enabled, summary_version, max_chars
    try:
        payload = tomli.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return enabled, summary_version, max_chars
    index_cfg = payload.get("index")
    enrichment = index_cfg.get("enrichment") if isinstance(index_cfg, dict) else None
    if not isinstance(enrichment, dict):
        return enabled, summary_version, max_chars
    if isinstance(enrichment.get("enabled"), bool):
        enabled = enrichment["enabled"]
    if isinstance(enrichment.get("summary_version"), int) and enrichment["summary_version"] > 0:
        summary_version = enrichment["summary_version"]
    if isinstance(enrichment.get("max_summary_chars"), int) and 80 <= enrichment["max_summary_chars"] <= 1000:
        max_chars = enrichment["max_summary_chars"]
    return enabled, summary_version, max_chars


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def generate_explain_summary(path: Path, *, max_chars: int) -> str:
    extension = path.suffix.lower() or "none"
    symbols = extract_python_symbols(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raw = ""
    first_line = _first_non_empty_line(raw) or ""
    line_count = len(raw.splitlines()) if raw else 0
    symbol_hint = ", ".join(symbols[:3]) if symbols else "no top-level python symbols"
    basis = (
        f"{path.name}: {extension} file with {line_count} lines; "
        f"symbols={symbol_hint}; first_line={first_line[:90]}."
    )
    return basis[:max_chars].strip()


def extension_guess(path: Path) -> str:
    return path.suffix.lower().lstrip(".") if path.suffix else "none"


def build_file_entry(
    root: Path,
    path: Path,
    *,
    enrichment_enabled: bool,
    summary_version: int,
    max_summary_chars: int,
    existing_file_entry: dict[str, object] | None,
    force_refresh: bool,
    enrichment_errors: list[str],
) -> dict[str, object]:
    rel_path = path.relative_to(root)
    path_class, state = classify_relative_path(rel_path)
    stat = path.stat()
    content_hash = optional_file_hash(path)
    entry = {
        "path": str(rel_path),
        "kind": "file",
        "extension": extension_guess(path),
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "hash": content_hash,
        "content_hash": content_hash,
        "top_level_symbols": extract_python_symbols(path),
        "path_class": path_class,
        "index_participation_state": state,
    }
    if not enrichment_enabled:
        return entry

    try:
        reuse_existing = False
        if not force_refresh and existing_file_entry:
            prev_hash = existing_file_entry.get("content_hash")
            prev_version = existing_file_entry.get("summary_version")
            prev_summary = existing_file_entry.get("explain_summary")
            prev_updated = existing_file_entry.get("summary_updated_at")
            if (
                isinstance(prev_summary, str)
                and prev_summary.strip()
                and prev_hash == content_hash
                and prev_version == summary_version
                and isinstance(prev_updated, str)
            ):
                reuse_existing = True
                entry["explain_summary"] = prev_summary
                entry["summary_version"] = prev_version
                entry["summary_updated_at"] = prev_updated
        if not reuse_existing:
            entry["explain_summary"] = generate_explain_summary(path, max_chars=max_summary_chars)
            entry["summary_version"] = summary_version
            entry["summary_updated_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:  # pragma: no cover - defensive
        enrichment_errors.append(f"{rel_path}: {exc}")
    return entry


def build_directory_entry(root: Path, path: Path) -> dict[str, object]:
    rel_path = path.relative_to(root) if path != root else Path(".")
    path_class, state = classify_relative_path(rel_path)
    depth = 0 if rel_path == Path(".") else len(rel_path.parts)
    child_files = 0
    child_dirs = 0
    ext_counter: Counter[str] = Counter()
    try:
        for child in path.iterdir():
            rel_child = child.relative_to(root)
            child_class, _state = classify_relative_path(rel_child)
            if child_class in {"hard_ignore", "index_exclude"}:
                continue
            if child.is_dir():
                child_dirs += 1
            elif child.is_file():
                child_files += 1
                ext_counter[extension_guess(child)] += 1
    except OSError:
        pass

    dominant = [ext for ext, _count in ext_counter.most_common(5)]
    return {
        "path": str(rel_path),
        "kind": "directory",
        "depth": depth,
        "child_file_count": child_files,
        "child_directory_count": child_dirs,
        "dominant_extensions": dominant,
        "path_class": path_class,
        "index_participation_state": state,
    }


def should_index(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    path_class, _state = classify_relative_path(rel)
    return path_class not in {"hard_ignore", "index_exclude"}


def build_index(repo_root: Path, request: CommandRequest, session: ExecutionSession) -> dict[str, object]:
    session.record_effect(EffectClass.READ_ONLY, "scan repository for index")
    enrichment_enabled, summary_version, max_summary_chars = load_index_enrichment_config(repo_root)
    force_refresh = request.payload.strip().lower() in {"refresh", "rebuild", "enrich-refresh", "full-refresh"}
    existing_index = load_existing_index(repo_root)
    existing_files = (
        existing_index.get("entries", {}).get("files", [])
        if isinstance(existing_index, dict)
        else []
    )
    existing_entry_map = _existing_entry_map(existing_index)
    existing_by_path: dict[str, dict[str, object]] = {}
    if isinstance(existing_files, list):
        for item in existing_files:
            if not isinstance(item, dict):
                continue
            p = item.get("path")
            if isinstance(p, str):
                existing_by_path[p] = item

    files: list[dict[str, object]] = []
    enrichment_errors: list[str] = []
    directories: list[dict[str, object]] = [build_directory_entry(repo_root, repo_root)]
    for current_root, dir_names, file_names in os.walk(repo_root, topdown=True):
        current_path = Path(current_root)
        rel_current = current_path.relative_to(repo_root) if current_path != repo_root else Path(".")

        # Prune traversals for hard-ignore and index_exclude directories.
        kept_dirs: list[str] = []
        for dir_name in dir_names:
            rel_dir = rel_current / dir_name if rel_current != Path(".") else Path(dir_name)
            path_class, _state = classify_relative_path(rel_dir)
            if path_class in {"hard_ignore", "index_exclude"}:
                continue
            kept_dirs.append(dir_name)
        dir_names[:] = kept_dirs

        if current_path != repo_root and should_index(current_path, repo_root):
            directories.append(build_directory_entry(repo_root, current_path))

        for file_name in file_names:
            file_path = current_path / file_name
            if should_index(file_path, repo_root):
                rel_str = str(file_path.relative_to(repo_root))
                files.append(
                    build_file_entry(
                        repo_root,
                        file_path,
                        enrichment_enabled=enrichment_enabled,
                        summary_version=summary_version,
                        max_summary_chars=max_summary_chars,
                        existing_file_entry=existing_by_path.get(rel_str),
                        force_refresh=force_refresh,
                        enrichment_errors=enrichment_errors,
                    )
                )

    new_entries = 0
    updated_entries = 0
    unchanged_entries = 0
    current_keys: set[tuple[str, str]] = set()
    for entry in [*directories, *files]:
        kind = entry.get("kind")
        path = entry.get("path")
        if not isinstance(kind, str) or not isinstance(path, str):
            continue
        key = (kind, path)
        current_keys.add(key)
        existing = existing_entry_map.get(key)
        if existing is None:
            new_entries += 1
        elif existing != entry:
            updated_entries += 1
        else:
            unchanged_entries += 1
    removed_entries = len(set(existing_entry_map.keys()) - current_keys)

    return {
        "version": 1,
        "capability": request.capability.value,
        "profile": request.profile.value,
        "root": str(repo_root),
        "entries": {
            "directories": directories,
            "files": files,
        },
        "counts": {
            "directories": len(directories),
            "files": len(files),
        },
        "delta": {
            "new_entries": new_entries,
            "updated_entries": updated_entries,
            "unchanged_entries": unchanged_entries,
            "removed_entries": removed_entries,
        },
        "enrichment": {
            "enabled": enrichment_enabled,
            "summary_version": summary_version,
            "max_summary_chars": max_summary_chars,
            "force_refresh": force_refresh,
            "errors": enrichment_errors[:50],
            "error_count": len(enrichment_errors),
        },
    }


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    print("=== FORGE INDEX ===")
    print(f"Profile: {request.profile.value}")
    if request.payload:
        print(f"Operation: {request.payload}")
    print(f"Root: {repo_root}")

    data = build_index(repo_root=repo_root, request=request, session=session)
    target = write_forge_file(
        root=repo_root,
        relative_path="index.json",
        content=json.dumps(data, indent=2, sort_keys=True),
        session=session,
    )
    print(f"Wrote index: {target}")
    print(
        "Indexed entries: "
        f"{data['counts']['directories']} directories, {data['counts']['files']} files"
    )
    delta = data.get("delta", {})
    if isinstance(delta, dict):
        print(
            "Index delta: "
            f"{delta.get('new_entries', 0)} new entries, "
            f"{delta.get('updated_entries', 0)} updated entries"
        )
    enrichment = data.get("enrichment", {})
    if isinstance(enrichment, dict):
        print(
            "Enrichment: "
            f"enabled={enrichment.get('enabled')} "
            f"summary_version={enrichment.get('summary_version')} "
            f"errors={enrichment.get('error_count')}"
        )
    graph_warning: str | None = None
    try:
        existing_graph, graph_load_warnings = load_repo_graph_with_warnings(repo_root, session)
        if graph_load_warnings:
            print(f"Graph cache: existing graph ignored ({graph_load_warnings[0]})")
        files_payload = data.get("entries", {}).get("files", [])
        file_entries = files_payload if isinstance(files_payload, list) else []
        graph_payload, graph_warnings = build_repo_graph(
            repo_root=repo_root,
            file_entries=file_entries,
            session=session,
            existing_graph=existing_graph,
        )
        graph_target = write_forge_file(
            root=repo_root,
            relative_path="graph.json",
            content=json.dumps(graph_payload, indent=2, sort_keys=True),
            session=session,
        )
        print(
            "Graph cache: "
            f"{graph_target} "
            f"(nodes={graph_payload.get('stats', {}).get('node_count', 0)}, "
            f"edges={graph_payload.get('stats', {}).get('edge_count', 0)}, "
            f"reused_files={graph_payload.get('stats', {}).get('reused_files', 0)}, "
            f"rebuilt_files={graph_payload.get('stats', {}).get('rebuilt_files', 0)})"
        )
        if graph_warnings:
            print(f"Graph warnings: {len(graph_warnings)} (showing first: {graph_warnings[0]})")
    except Exception as exc:  # pragma: no cover - defensive
        graph_warning = f"graph build skipped due to error: {exc}"
        print(f"Graph cache: {graph_warning}")
    if graph_warning is not None:
        data.setdefault("graph", {})
        if isinstance(data["graph"], dict):
            data["graph"]["warning"] = graph_warning
    return 0
