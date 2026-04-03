from __future__ import annotations

import re
from collections import Counter
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
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.repo_io import iter_repo_files, read_text_file


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

def detect_languages(files: list[Path]) -> list[str]:
    counter: Counter[str] = Counter()
    for path in files:
        lang = LANGUAGE_BY_EXTENSION.get(path.suffix.lower())
        if lang:
            counter[lang] += 1
    return [lang for lang, _count in counter.most_common(6)]


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
    important_names = {
        "readme.md",
        "license",
        "pyproject.toml",
        "package.json",
        "forge.py",
        "main.py",
        "setup.py",
    }
    important: list[Path] = []
    for path in files:
        rel = path.relative_to(repo_root)
        name = rel.name.lower()
        if name in important_names:
            important.append(rel)
        elif len(rel.parts) <= 2 and ("cli" in name or "main" in name):
            important.append(rel)
    # dedupe preserving order
    seen: set[Path] = set()
    result: list[Path] = []
    for path in important:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result[:10]


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
) -> tuple[dict[str, object], str | None]:
    languages = detect_languages(files)
    frameworks = detect_framework_hints(files, repo_root, session, limit=80 if request.profile != Profile.SIMPLE else 25)
    directories = directories_from_index_payload(index_payload)
    if not directories:
        directories = top_directories(files, repo_root)
    important = find_important_files(files, repo_root)
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
        "key_components": [{"path": directory, "file_count": count} for directory, count in directories[:6]],
        "technologies": {
            "languages": languages,
            "framework_hints": frameworks,
        },
        "important_files": [str(path) for path in important],
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
) -> dict[str, object]:
    rel = target.path.relative_to(repo_root)
    files: list[Path]
    if target.kind == "directory":
        files = list_directory_files(target.path, repo_root, session)
    else:
        files = [target.path]
    languages = detect_languages(files)

    key_components: list[dict[str, object]] = []
    if target.kind == "directory":
        subdirs = Counter(p.relative_to(target.path).parts[0] for p in files if len(p.relative_to(target.path).parts) > 1)
        for name, count in subdirs.most_common(6):
            key_components.append({"name": name, "file_count": count})
    else:
        content = read_text_file(target.path, session) or ""
        defs = re.findall(r"^\s*(?:def|class)\s+([A-Za-z0-9_]+)", content, flags=re.MULTILINE)
        key_components = [{"symbol": name} for name in defs[:8]]

    important_files: list[str] = []
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        if target.kind == "directory":
            important_files = [str(item) for item in find_important_files(files, repo_root)[:8]]
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
) -> str | None:
    languages = detect_languages(files)
    frameworks = detect_framework_hints(files, repo_root, session, limit=80 if request.profile != Profile.SIMPLE else 25)
    directories = directories_from_index_payload(index_payload)
    if not directories:
        directories = top_directories(files, repo_root)
    important = find_important_files(files, repo_root)
    print("\n--- Summary ---")
    print(summary)

    print("\n--- Key Components ---")
    if directories:
        component_limit = 3 if view == "standard" else 6
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
) -> None:
    rel = target.path.relative_to(repo_root)
    print("\n--- Summary ---")
    print(summary)

    files: list[Path]
    if target.kind == "directory":
        files = list_directory_files(target.path, repo_root, session)
    else:
        files = [target.path]

    languages = detect_languages(files)
    print("\n--- Key Components ---")
    if target.kind == "directory":
        subdirs = Counter(p.relative_to(target.path).parts[0] for p in files if len(p.relative_to(target.path).parts) > 1)
        if subdirs:
            for name, count in subdirs.most_common(6):
                print(f"- {name}: {count} files")
        else:
            print("- Target directory has mostly flat file structure.")
    else:
        content = read_text_file(target.path, session) or ""
        defs = re.findall(r"^\s*(?:def|class)\s+([A-Za-z0-9_]+)", content, flags=re.MULTILINE)
        if defs:
            symbol_limit = 4 if view == "standard" else 8
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
                important_limit = 3 if view == "standard" else 8
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
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
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
        return evidence

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
    return evidence


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    target = resolve_describe_target(repo_root, request.payload, session)
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

    next_step: str | None = None
    llm_settings = resolve_settings(args, repo_root)
    llm_outcome = None
    evidence_payload: list[dict[str, object]] = []
    sections: dict[str, object] = {}
    if target.kind == "repo":
        files = files_from_index_payload(repo_root, index)
        if not files:
            files = iter_repo_files(repo_root, session)
        deterministic_summary = infer_repo_summary(repo_root, files, detect_languages(files), session)
        evidence_payload = collect_describe_evidence(target=target, repo_root=repo_root, files=files)
        llm_outcome = maybe_refine_summary(
            capability=request.capability,
            profile=request.profile,
            task=request.payload or "repository overview",
            deterministic_summary=deterministic_summary,
            evidence=evidence_payload,
            settings=llm_settings,
            repo_root=repo_root,
        )
        sections, next_step = collect_repo_sections(repo_root, files, request, session, index)
        if not is_json:
            next_step = print_repo_description(
                repo_root,
                files,
                request,
                session,
                index,
                llm_outcome.summary,
                view,
            )
    else:
        files = list_directory_files(target.path, repo_root, session) if target.kind == "directory" else [target.path]
        deterministic_summary = infer_target_summary(target, repo_root, session)
        evidence_payload = collect_describe_evidence(target=target, repo_root=repo_root, files=files)
        llm_outcome = maybe_refine_summary(
            capability=request.capability,
            profile=request.profile,
            task=request.payload,
            deterministic_summary=deterministic_summary,
            evidence=evidence_payload,
            settings=llm_settings,
            repo_root=repo_root,
        )
        sections = collect_target_sections(target, repo_root, request, session)
        if not is_json:
            print_target_description(target, repo_root, request, session, llm_outcome.summary, view)

    uncertainty: list[str] = []
    if target.kind == "symbol":
        uncertainty.append("Symbol targets are resolved via best-effort matching.")
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
        sections["llm_usage"] = llm_outcome.usage
        sections["provenance"] = provenance_section(
            llm_used=bool(llm_outcome.usage.get("used")),
            evidence_count=len(evidence_payload),
        )

    if is_json:
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=llm_outcome.summary if llm_outcome else deterministic_summary,
            evidence=evidence_payload,
            uncertainty=uncertainty,
            next_step=resolved_next_step,
            sections=sections,
        )
        emit_contract_json(contract)
        return 0

    print("\n--- Uncertainty ---")
    notes = uncertainty if is_full(view) else uncertainty[:1]
    for note in notes:
        print(f"- {note}")
    if llm_outcome and is_full(view):
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
    print("\n--- Next Step ---")
    print(resolved_next_step)
    return 0
