from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import (
    ResolvedTarget,
    list_directory_files,
    load_index_payload,
    resolve_describe_target,
)
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import maybe_refine_summary, resolve_settings
from core.llm_integration import provenance_section
from core.mode_orchestrator import iter_bounded_cycles
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.repo_io import iter_repo_files, read_text_file
from core.run_reference import RunReferenceError, resolve_from_run_payload


LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React JSX",
    ".tsx": "React TSX",
    ".php": "PHP",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
}


@dataclass(frozen=True)
class DescribePolicy:
    framework_hints_max_files: int
    languages_max_items: int
    components_max_items: int
    important_files_max_items: int
    symbols_max_items: int


def _resolve_runtime_int(args, key: str, default: int, *, min_value: int = 1, max_value: int = 2000) -> tuple[int, str]:
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


def detect_languages(files: list[Path], limit: int) -> list[str]:
    counter: Counter[str] = Counter()
    for path in files:
        lang = LANGUAGE_BY_EXTENSION.get(path.suffix.lower())
        if lang:
            counter[lang] += 1
    return [lang for lang, _count in counter.most_common(limit)]


def detect_framework_hints(files: list[Path], repo_root: Path, session: ExecutionSession, limit: int) -> list[str]:
    hints: list[str] = []
    patterns = [
        ("argparse", re.compile(r"^\s*(?:from|import)\s+argparse\b", re.MULTILINE)),
        ("pytest", re.compile(r"^\s*(?:from|import)\s+pytest\b", re.MULTILINE)),
        ("flask", re.compile(r"^\s*(?:from|import)\s+flask\b", re.MULTILINE)),
        ("fastapi", re.compile(r"^\s*(?:from|import)\s+fastapi\b", re.MULTILINE)),
        ("django", re.compile(r"^\s*(?:from|import)\s+django\b", re.MULTILINE)),
        ("react", re.compile(r"\bfrom\s+['\"]react['\"]|^\s*import\s+react\b", re.IGNORECASE | re.MULTILINE)),
        ("sqlalchemy", re.compile(r"^\s*(?:from|import)\s+sqlalchemy\b", re.MULTILINE)),
    ]
    found: set[str] = set()
    code_ext = {".py", ".js", ".jsx", ".ts", ".tsx", ".php"}
    scoped_files = [path for path in files if path.suffix.lower() in code_ext][:limit]
    for path in scoped_files:
        content = read_text_file(path, session)
        if not content:
            continue
        for label, pattern in patterns:
            if label in found:
                continue
            if pattern.search(content):
                found.add(label)
                hints.append(label)
    return hints


def top_directories(files: list[Path], repo_root: Path, depth: int = 1) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for path in files:
        rel = path.relative_to(repo_root)
        parts = rel.parts
        if not parts:
            continue
        key = "." if len(parts) == 1 else "/".join(parts[:depth])
        counter[key] += 1
    return counter.most_common(8)


def directories_from_index_payload(index_payload: dict[str, object] | None) -> list[tuple[str, int]]:
    if not index_payload:
        return []
    entries = index_payload.get("entries", {})
    directories = entries.get("directories", []) if isinstance(entries, dict) else []
    if not isinstance(directories, list):
        return []

    ranked: list[tuple[str, int]] = []
    for entry in directories:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        file_count = entry.get("child_file_count", 0)
        if not isinstance(path, str) or path in {"."}:
            continue
        if not isinstance(file_count, int):
            file_count = 0
        ranked.append((path, file_count))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def files_from_index_payload(repo_root: Path, index_payload: dict[str, object] | None) -> list[Path]:
    if not index_payload:
        return []
    entries = index_payload.get("entries", {})
    files = entries.get("files", []) if isinstance(entries, dict) else []
    if not isinstance(files, list):
        return []

    results: list[Path] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if isinstance(rel, str):
            results.append(repo_root / rel)
    return results


def find_important_files(files: list[Path], repo_root: Path) -> list[Path]:
    return [item["path"] for item in rank_important_files(files, repo_root, limit=10)]


def rank_important_files(files: list[Path], repo_root: Path, limit: int = 10) -> list[dict[str, object]]:
    important_names = {
        "readme.md",
        "license",
        "pyproject.toml",
        "package.json",
        "forge.py",
        "main.py",
        "setup.py",
    }
    preferred_top = {"src", "core", "modes", "cmd"}
    noise_markers = {"tests", "test", "fixtures", "fixture", "example", "examples", "sample", "samples"}
    ranked: list[dict[str, object]] = []
    for path in files:
        rel = path.relative_to(repo_root)
        name = rel.name.lower()
        parts = [part.lower() for part in rel.parts]
        score = 0
        rationale: list[str] = []

        if name in important_names:
            score += 30
            rationale.append("conventional_entry_or_config_name")
        if len(parts) == 1:
            score += 12
            rationale.append("root_proximity")
        elif len(parts) == 2:
            score += 8
            rationale.append("near_root_proximity")
        elif len(parts) >= 4:
            score -= 2
        if parts and parts[0] in preferred_top:
            score += 6
            rationale.append("primary_project_area")
        if len(parts) <= 2 and ("cli" in name or "main" in name):
            score += 8
            rationale.append("entrypoint_like_name")
        if any(marker in parts for marker in noise_markers):
            score -= 18
            rationale.append("fixture_or_test_subtree_deprioritized")
        if name.startswith("test_") or "/tests/" in f"/{'/'.join(parts)}/":
            score -= 6
            rationale.append("test_like_path_deprioritized")

        if score <= 0:
            continue
        ranked.append({"path": rel, "score": score, "rationale": rationale})

    ranked.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    deduped: list[dict[str, object]] = []
    seen_paths: set[Path] = set()
    for item in ranked:
        rel_path = item["path"]
        if not isinstance(rel_path, Path):
            continue
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def infer_repo_summary(
    repo_root: Path,
    files: list[Path],
    languages: list[str],
    session: ExecutionSession,
) -> str:
    readme = repo_root / "README.md"
    if readme.exists():
        text = read_text_file(readme, session)
        if text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for line in lines:
                if line.startswith("# "):
                    continue
                if len(line) > 30:
                    return line
    if not files:
        return "Repository currently has no readable source files."
    lang_part = ", ".join(languages) if languages else "mixed languages"
    return f"Repository appears to be a {lang_part} project with {len(files)} readable files."


def infer_target_summary(target: ResolvedTarget, repo_root: Path, session: ExecutionSession) -> str:
    rel = target.path.relative_to(repo_root)
    if target.kind == "directory":
        return f"{rel} is a directory-level subsystem with grouped repository content."
    if target.kind == "symbol":
        return f"{target.kind} target resolves to {rel}, likely containing the requested logic."
    content = read_text_file(target.path, session)
    if not content:
        return f"{rel} is a file target."
    line_count = len(content.splitlines())
    if "argparse" in content:
        return f"{rel} appears to define CLI behavior and argument handling."
    if "class " in content or "def " in content:
        return f"{rel} is implementation-oriented source code ({line_count} lines)."
    return f"{rel} is a project file ({line_count} lines)."


def collect_repo_sections(
    repo_root: Path,
    files: list[Path],
    request: CommandRequest,
    session: ExecutionSession,
    index_payload: dict[str, object] | None,
    policy: DescribePolicy,
) -> tuple[dict[str, object], str | None]:
    languages = detect_languages(files, policy.languages_max_items)
    framework_scan_limit = policy.framework_hints_max_files
    if request.profile == Profile.SIMPLE:
        framework_scan_limit = min(framework_scan_limit, 25)
    frameworks = detect_framework_hints(files, repo_root, session, limit=framework_scan_limit)
    directories = directories_from_index_payload(index_payload)
    if not directories:
        directories = top_directories(files, repo_root)
    ranked_important = rank_important_files(files, repo_root, limit=policy.important_files_max_items)
    important = [item["path"] for item in ranked_important if isinstance(item.get("path"), Path)]
    architecture_notes: list[str] = []
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        if any(path.relative_to(repo_root).parts and path.relative_to(repo_root).parts[0] == "cmd" for path in files):
            architecture_notes.append("CLI-oriented structure detected (`cmd/` present).")
        if any(path.relative_to(repo_root).parts and path.relative_to(repo_root).parts[0] == "modes" for path in files):
            architecture_notes.append("Capability-style mode separation detected (`modes/` present).")
        if any(path.relative_to(repo_root).parts and path.relative_to(repo_root).parts[0] == "core" for path in files):
            architecture_notes.append("Shared core logic appears centralized in `core/`.")

    sections: dict[str, object] = {
        "target": {"kind": "repo", "path": "."},
        "key_components": [
            {"path": directory, "file_count": count}
            for directory, count in directories[: policy.components_max_items]
        ],
        "technologies": {
            "languages": languages,
            "framework_hints": frameworks,
        },
        "important_files": [str(path) for path in important],
        "important_file_rationale": [
            {
                "path": str(item["path"]),
                "score": item["score"],
                "rationale": item["rationale"],
            }
            for item in ranked_important
        ],
        "architecture_notes": architecture_notes,
    }
    if request.profile == Profile.DETAILED:
        sections["readme_draft_snippet"] = (
            "This repository provides a structured toolchain focused on explicit capabilities, "
            "with readable command flows and audit-friendly outputs."
        )
    next_step = str(important[0]) if important else None
    return sections, next_step


def collect_target_sections(
    target: ResolvedTarget,
    repo_root: Path,
    request: CommandRequest,
    session: ExecutionSession,
    policy: DescribePolicy,
) -> dict[str, object]:
    rel = target.path.relative_to(repo_root)
    files: list[Path]
    if target.kind == "directory":
        files = list_directory_files(target.path, repo_root, session)
    else:
        files = [target.path]
    languages = detect_languages(files, policy.languages_max_items)

    key_components: list[dict[str, object]] = []
    if target.kind == "directory":
        subdirs = Counter(p.relative_to(target.path).parts[0] for p in files if len(p.relative_to(target.path).parts) > 1)
        for name, count in subdirs.most_common(policy.components_max_items):
            key_components.append({"name": name, "file_count": count})
    else:
        content = read_text_file(target.path, session) or ""
        defs = re.findall(r"^\s*(?:def|class)\s+([A-Za-z0-9_]+)", content, flags=re.MULTILINE)
        key_components = [{"symbol": name} for name in defs[: policy.symbols_max_items]]

    important_files: list[str] = []
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        if target.kind == "directory":
            important_files = [str(item) for item in find_important_files(files, repo_root)[: policy.important_files_max_items]]
        else:
            important_files = [str(rel)]

    architecture_notes: list[str] = []
    if request.profile == Profile.DETAILED:
        if target.kind == "symbol":
            architecture_notes.append("Target was resolved via symbol matching; verify semantic intent with `forge explain`.")
        elif target.kind == "directory":
            architecture_notes.append("Directory-level description is based on file distribution and naming patterns.")
        else:
            architecture_notes.append("File-level description is based on structural tokens and naming conventions.")

    return {
        "target": {"kind": target.kind, "path": str(rel), "source": target.source},
        "key_components": key_components,
        "technologies": {"languages": languages},
        "important_files": important_files,
        "architecture_notes": architecture_notes,
    }


def print_repo_description(
    repo_root: Path,
    files: list[Path],
    request: CommandRequest,
    session: ExecutionSession,
    index_payload: dict[str, object] | None,
    summary: str,
    view: str,
    policy: DescribePolicy,
) -> str | None:
    languages = detect_languages(files, policy.languages_max_items)
    framework_scan_limit = policy.framework_hints_max_files
    if request.profile == Profile.SIMPLE:
        framework_scan_limit = min(framework_scan_limit, 25)
    frameworks = detect_framework_hints(files, repo_root, session, limit=framework_scan_limit)
    directories = directories_from_index_payload(index_payload)
    if not directories:
        directories = top_directories(files, repo_root)
    ranked_important = rank_important_files(files, repo_root, limit=policy.important_files_max_items)
    important = [item["path"] for item in ranked_important if isinstance(item.get("path"), Path)]
    print("\n--- Summary ---")
    print(summary)

    print("\n--- Key Components ---")
    if directories:
        component_limit = 3 if view == "standard" else policy.components_max_items
        for directory, count in directories[:component_limit]:
            print(f"- {directory}: {count} files")
    else:
        print("- No major directories detected")

    print("\n--- Technologies ---")
    print(f"Languages: {', '.join(languages) if languages else 'unknown'}")
    print(f"Framework hints: {', '.join(frameworks) if frameworks else 'none detected'}")

    print("\n--- Important Files ---")
    if important:
        important_limit = 3 if view == "standard" else len(important)
        for path in important[:important_limit]:
            print(f"- {path}")
    else:
        print("- No obvious entry files detected")

    if request.profile in {Profile.STANDARD, Profile.DETAILED} and is_full(view):
        print("\n--- Architecture Notes ---")
        if any(path.relative_to(repo_root).parts and path.relative_to(repo_root).parts[0] == "cmd" for path in files):
            print("- CLI-oriented structure detected (`cmd/` present).")
        if any(path.relative_to(repo_root).parts and path.relative_to(repo_root).parts[0] == "modes" for path in files):
            print("- Capability-style mode separation detected (`modes/` present).")
        if any(path.relative_to(repo_root).parts and path.relative_to(repo_root).parts[0] == "core" for path in files):
            print("- Shared core logic appears centralized in `core/`.")

    if request.profile == Profile.DETAILED and is_full(view):
        print("\n--- README Draft Snippet ---")
        print(
            "This repository provides a structured toolchain focused on explicit capabilities, "
            "with readable command flows and audit-friendly outputs."
        )

    return str(important[0]) if important else None


def print_target_description(
    target: ResolvedTarget,
    repo_root: Path,
    request: CommandRequest,
    session: ExecutionSession,
    summary: str,
    view: str,
    policy: DescribePolicy,
) -> None:
    rel = target.path.relative_to(repo_root)
    print("\n--- Summary ---")
    print(summary)

    files: list[Path]
    if target.kind == "directory":
        files = list_directory_files(target.path, repo_root, session)
    else:
        files = [target.path]

    languages = detect_languages(files, policy.languages_max_items)
    print("\n--- Key Components ---")
    if target.kind == "directory":
        subdirs = Counter(p.relative_to(target.path).parts[0] for p in files if len(p.relative_to(target.path).parts) > 1)
        if subdirs:
            for name, count in subdirs.most_common(policy.components_max_items):
                print(f"- {name}: {count} files")
        else:
            print("- Target directory has mostly flat file structure.")
    else:
        content = read_text_file(target.path, session) or ""
        defs = re.findall(r"^\s*(?:def|class)\s+([A-Za-z0-9_]+)", content, flags=re.MULTILINE)
        if defs:
            symbol_limit = 4 if view == "standard" else policy.symbols_max_items
            for name in defs[:symbol_limit]:
                print(f"- symbol: {name}")
        else:
            print("- No top-level definitions detected.")

    print("\n--- Technologies ---")
    print(f"Languages: {', '.join(languages) if languages else 'unknown'}")

    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        print("\n--- Important Files ---")
        if target.kind == "directory":
            important = find_important_files(files, repo_root)
            if important:
                important_limit = 3 if view == "standard" else policy.important_files_max_items
                for item in important[:important_limit]:
                    print(f"- {item}")
            else:
                print("- No conventional entry/config files found in target.")
        else:
            print(f"- {rel}")

    if request.profile == Profile.DETAILED and is_full(view):
        print("\n--- Architecture Notes ---")
        if target.kind == "symbol":
            print("- Target was resolved via symbol matching; verify semantic intent with `forge explain`.")
        elif target.kind == "directory":
            print("- Directory-level description is based on file distribution and naming patterns.")
        else:
            print("- File-level description is based on structural tokens and naming conventions.")


def collect_describe_evidence(
    *,
    target: ResolvedTarget,
    repo_root: Path,
    files: list[Path],
    requested_symbol: str | None = None,
) -> tuple[list[dict[str, object]], bool]:
    evidence: list[dict[str, object]] = []
    symbol_anchor_found = False
    if target.kind in {"repo", "directory"}:
        label = "visible repository file" if target.kind == "repo" else "file within described directory"
        for path in files[:10]:
            evidence.append(
                {
                    "path": str(path.relative_to(repo_root)),
                    "line": 1,
                    "text": label,
                }
            )
        return evidence, symbol_anchor_found

    if target.kind == "symbol":
        raw_symbol = (requested_symbol or "").strip()
        symbol_patterns: list[re.Pattern[str]] = []
        if raw_symbol:
            symbol_patterns.append(re.compile(rf"^\s*def\s+{re.escape(raw_symbol)}\s*\("))
            symbol_patterns.append(re.compile(rf"^\s*class\s+{re.escape(raw_symbol)}\s*[\(:]"))
        symbol_patterns.append(re.compile(r"^\s*(?:def|class)\s+[A-Za-z_][A-Za-z0-9_]*\s*[\(:]"))

        for idx, line in enumerate(target.content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if any(pattern.search(line) for pattern in symbol_patterns):
                evidence.append(
                    {
                        "path": str(target.path.relative_to(repo_root)),
                        "line": idx,
                        "text": stripped,
                    }
                )
                symbol_anchor_found = True
                break

    for idx, line in enumerate(target.content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        evidence.append(
            {
                "path": str(target.path.relative_to(repo_root)),
                "line": idx,
                "text": stripped,
            }
        )
        if len(evidence) >= 8:
            break
    return evidence, symbol_anchor_found


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
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
    orchestration_catalog = ["resolve_target", "collect_context", "synthesize", "summarize", "finalize"]
    orchestration_actions: list[dict[str, object]] = []

    def mark_action(name: str, status: str, detail: str) -> None:
        orchestration_actions.append({"action": name, "status": status, "detail": detail})

    explicit_target = bool(request.payload.strip())
    target = resolve_describe_target(repo_root, request.payload, session)
    mark_action("resolve_target", "completed", f"resolved kind={target.kind} source={target.source}")
    is_json = args.output_format == "json"
    view = resolve_view(args)

    if not is_json:
        print("=== FORGE DESCRIBE ===")
        print(f"Profile: {request.profile.value}")
        if request.payload:
            print(f"Target: {request.payload}")

    index = None
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        index = load_index_payload(repo_root, session)
    if not is_json:
        if index is not None:
            print("Index: loaded .forge/index.json")
        elif request.profile in {Profile.STANDARD, Profile.DETAILED}:
            print("Index: not available, scanning repository directly")

    framework_hints_max_files, framework_hints_source = _resolve_runtime_int(
        args,
        "describe.framework_hints.max_files",
        80,
        min_value=1,
        max_value=5000,
    )
    languages_max_items, languages_source = _resolve_runtime_int(
        args,
        "describe.languages.max_items",
        6,
        min_value=1,
        max_value=100,
    )
    components_max_items, components_source = _resolve_runtime_int(
        args,
        "describe.components.max_items",
        6,
        min_value=1,
        max_value=100,
    )
    important_files_max_items, important_files_source = _resolve_runtime_int(
        args,
        "describe.important_files.max_items",
        10,
        min_value=1,
        max_value=100,
    )
    symbols_max_items, symbols_source = _resolve_runtime_int(
        args,
        "describe.symbols.max_items",
        8,
        min_value=1,
        max_value=100,
    )
    describe_policy = DescribePolicy(
        framework_hints_max_files=framework_hints_max_files,
        languages_max_items=languages_max_items,
        components_max_items=components_max_items,
        important_files_max_items=important_files_max_items,
        symbols_max_items=symbols_max_items,
    )
    describe_policy_section = {
        "values": {
            "framework_hints_max_files": describe_policy.framework_hints_max_files,
            "languages_max_items": describe_policy.languages_max_items,
            "components_max_items": describe_policy.components_max_items,
            "important_files_max_items": describe_policy.important_files_max_items,
            "symbols_max_items": describe_policy.symbols_max_items,
        },
        "sources": {
            "framework_hints_max_files": framework_hints_source,
            "languages_max_items": languages_source,
            "components_max_items": components_source,
            "important_files_max_items": important_files_source,
            "symbols_max_items": symbols_source,
        },
    }

    if explicit_target and target.kind == "repo" and target.source == "fallback":
        summary = "Explicit describe target could not be resolved."
        uncertainty = [
            "explicit target did not resolve to a readable path or symbol",
            "describe did not fallback to repository overview for unresolved explicit target",
        ]
        next_step = 'Run: forge query "where is the relevant logic implemented?"'
        sections = {
            "target": {"kind": "unresolved", "path": request.payload, "source": "explicit_unresolved"},
            "important_files": [],
            "important_file_rationale": [],
            "key_components": [],
            "technologies": {"languages": [], "framework_hints": []},
            "architecture_notes": [],
            "describe_policy": describe_policy_section,
            "status": "unresolved_target",
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
        }
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=[],
            uncertainty=uncertainty,
            next_step=next_step,
            sections=sections,
        )
        if args.output_format == "json":
            emit_contract_json(contract)
            return 0
        print("\n--- Summary ---")
        print(summary)
        print("\n--- Uncertainty ---")
        for note in uncertainty:
            print(f"- {note}")
        print("\n--- Next Step ---")
        print(next_step)
        return 0

    next_step: str | None = None
    llm_settings = resolve_settings(args, repo_root)
    llm_outcome = None
    evidence_payload: list[dict[str, object]] = []
    symbol_anchor_found = False
    sections: dict[str, object] = {}
    done_reason = "completed"
    cycle = next(iter_bounded_cycles(max_iterations=1, max_wall_time_ms=1200))
    if cycle.wall_time_exhausted:
        done_reason = "wall_time_exhausted"
        mark_action("collect_context", "skipped", "orchestration wall time exhausted")
        deterministic_summary = "Describe orchestration budget exhausted before context collection."
        uncertainty = ["Describe orchestration exhausted configured wall-time budget before analysis started."]
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=deterministic_summary,
            evidence=[],
            uncertainty=uncertainty,
            next_step='Run: forge describe --view full',
            sections={
                "target": {"kind": target.kind, "path": str(target.path.relative_to(repo_root)), "source": target.source},
                "action_orchestration": {
                    "catalog": orchestration_catalog,
                    "iterations": [{"iteration": 1, "actions": orchestration_actions}],
                    "done_reason": done_reason,
                    "usage": {
                        "engine": "core.mode_orchestrator.iter_bounded_cycles",
                        "max_iterations": 1,
                        "max_wall_time_ms": 1200,
                    },
                },
            },
        )
        if is_json:
            emit_contract_json(contract)
            return 0
        print("\n--- Summary ---")
        print(deterministic_summary)
        print("\n--- Uncertainty ---")
        for note in uncertainty:
            print(f"- {note}")
        print("\n--- Next Step ---")
        print('Run: forge describe --view full')
        return 0
    if target.kind == "repo":
        files = files_from_index_payload(repo_root, index)
        if not files:
            files = iter_repo_files(repo_root, session)
        mark_action("collect_context", "completed", f"collected repo context from {len(files)} files")
        deterministic_summary = infer_repo_summary(repo_root, files, detect_languages(files, describe_policy.languages_max_items), session)
        mark_action("synthesize", "completed", "assembled repository-level deterministic summary")
        evidence_payload, symbol_anchor_found = collect_describe_evidence(
            target=target,
            repo_root=repo_root,
            files=files,
            requested_symbol=request.payload if target.kind == "symbol" else None,
        )
        llm_outcome = maybe_refine_summary(
            capability=request.capability,
            profile=request.profile,
            task=request.payload or "repository overview",
            deterministic_summary=deterministic_summary,
            evidence=evidence_payload,
            settings=llm_settings,
            repo_root=repo_root,
        )
        sections, next_step = collect_repo_sections(repo_root, files, request, session, index, describe_policy)
        if not is_json:
            next_step = print_repo_description(
                repo_root,
                files,
                request,
                session,
                index,
                llm_outcome.summary,
                view,
                describe_policy,
            )
    else:
        files = list_directory_files(target.path, repo_root, session) if target.kind == "directory" else [target.path]
        mark_action("collect_context", "completed", f"collected target context from {len(files)} file(s)")
        deterministic_summary = infer_target_summary(target, repo_root, session)
        mark_action("synthesize", "completed", "assembled target-level deterministic summary")
        evidence_payload, symbol_anchor_found = collect_describe_evidence(
            target=target,
            repo_root=repo_root,
            files=files,
            requested_symbol=request.payload if target.kind == "symbol" else None,
        )
        llm_outcome = maybe_refine_summary(
            capability=request.capability,
            profile=request.profile,
            task=request.payload,
            deterministic_summary=deterministic_summary,
            evidence=evidence_payload,
            settings=llm_settings,
            repo_root=repo_root,
        )
        sections = collect_target_sections(target, repo_root, request, session, describe_policy)
        if not is_json:
            print_target_description(target, repo_root, request, session, llm_outcome.summary, view, describe_policy)

    uncertainty: list[str] = []
    if target.kind == "symbol":
        uncertainty.append("Symbol targets are resolved via best-effort matching.")
        if not symbol_anchor_found:
            uncertainty.append("Requested symbol anchor was not found in evidence; confidence is reduced.")
    elif target.kind == "repo" and index is None and request.profile in {Profile.STANDARD, Profile.DETAILED}:
        uncertainty.append("Index not available; summary is based on direct repository scan.")
    else:
        uncertainty.append("Summary is heuristic and based on visible structure/signals.")
    if llm_outcome:
        uncertainty.extend(llm_outcome.uncertainty_notes)

    if target.kind == "repo":
        resolved_next_step = (
            f"Run: forge explain {next_step}" if next_step else 'Run: forge query "where is the main entrypoint"'
        )
    else:
        rel = target.path.relative_to(repo_root)
        resolved_next_step = f"Run: forge explain {rel}"

    if llm_outcome:
        mark_action("summarize", "completed", "applied deterministic+llm summary step")
        sections["llm_usage"] = llm_outcome.usage
        sections["provenance"] = provenance_section(
            llm_used=bool(llm_outcome.usage.get("used")),
            evidence_count=len(evidence_payload),
        )
    sections["describe_policy"] = describe_policy_section
    mark_action("finalize", "completed", "assembled final output contract")
    sections["action_orchestration"] = {
        "catalog": orchestration_catalog,
        "iterations": [{"iteration": 1, "actions": orchestration_actions}],
        "done_reason": done_reason,
        "usage": {
            "engine": "core.mode_orchestrator.iter_bounded_cycles",
            "max_iterations": 1,
            "max_wall_time_ms": 1200,
        },
    }
    if from_run_meta:
        sections.update(from_run_meta)

    contract = build_contract(
        capability=request.capability.value,
        profile=request.profile.value,
        summary=llm_outcome.summary if llm_outcome else deterministic_summary,
        evidence=evidence_payload,
        uncertainty=uncertainty,
        next_step=resolved_next_step,
        sections=sections,
    )
    if is_json:
        emit_contract_json(contract)
        return 0

    print("\n--- Uncertainty ---")
    notes = uncertainty if is_full(view) else uncertainty[:1]
    for note in notes:
        print(f"- {note}")
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
    if llm_outcome and is_full(view):
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
    print("\n--- Next Step ---")
    print(resolved_next_step)
    return 0
