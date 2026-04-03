from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import (
    ResolvedTarget,
    find_related_files,
    load_index_entry_map,
    load_index_path_class_map,
    path_class_weight,
    prioritize_paths_by_index,
    resolve_file_or_symbol_target,
)
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import maybe_refine_summary, provenance_section, resolve_settings
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.repo_io import read_text_file


@dataclass
class Evidence:
    path: Path
    line: int
    text: str


ROLE_MARKERS = {
    "entrypoint": ["if __name__ == \"__main__\":", "argparse.ArgumentParser(", "main("],
    "configuration": [".yml", ".yaml", ".toml", ".ini", "config", "settings"],
    "support code": ["helper", "util", "common", "shared", "support"],
}


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


def uncertainty_notes(target: ResolvedTarget, evidence: list[Evidence], profile: Profile) -> list[str]:
    notes: list[str] = []
    if target.source == "symbol":
        notes.append("target was resolved via best-effort symbol matching across files")
    if len(evidence) < 3:
        notes.append("limited structural evidence found in target")
    if profile == Profile.SIMPLE:
        notes.append("simple profile uses target-local analysis only")
    return notes


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
) -> None:
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
        path_display = item.path.relative_to(repo_root)
        print(f"{path_display}:{item.line}: {item.text}")

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


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    view = resolve_view(args)
    repo_root = Path(args.repo_root).resolve()
    raw_target = request.payload.strip()

    target = resolve_file_or_symbol_target(repo_root, raw_target, session)

    if target is None:
        summary = "Target could not be resolved to a readable file or known symbol."
        uncertainty = [
            "no matching file path under repo root",
            "no symbol-like match found in readable text files",
        ]
        next_step = 'Run: forge query "where is this symbol defined?"'
        if args.output_format == "json":
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary=summary,
                evidence=[],
                uncertainty=uncertainty,
                next_step=next_step,
                sections={"role_classification": None, "related_files": []},
            )
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

    rel_target = target.path.relative_to(repo_root)
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
    evidence = gather_evidence_for_target(target, request)
    related: list[Path] = []
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        related_rel = find_related_files(repo_root, rel_target, session, limit=10)
        related_abs = [repo_root / rel for rel in related_rel]
        prioritized = prioritize_paths_by_index(
            repo_root,
            related_abs,
            path_classes,
            exclude_non_index_participating=True,
        )
        if not prioritized:
            prioritized = related_abs
        related = [path.relative_to(repo_root) for path in prioritized[:5]]
    uncertainties = uncertainty_notes(target, evidence, request.profile)
    next_step = f"Run: forge review {rel_target}"
    evidence_payload = [
        {
            "path": str(item.path.relative_to(repo_root)),
            "line": item.line,
            "text": item.text,
        }
        for item in evidence
    ]
    sections = {
        "role_classification": {"role": role, "reason": rationale},
        "related_files": [str(path) for path in related],
        "resolved_target": str(rel_target),
    }
    deterministic_summary = f"{rel_target} is primarily {role}."
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
    uncertainties.extend(llm_outcome.uncertainty_notes)
    sections["llm_usage"] = llm_outcome.usage
    sections["provenance"] = provenance_section(
        llm_used=bool(llm_outcome.usage.get("used")),
        evidence_count=len(evidence_payload),
    )

    if args.output_format == "json":
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=evidence_payload,
            uncertainty=uncertainties,
            next_step=next_step,
            sections=sections,
        )
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
    )
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
    return 0
