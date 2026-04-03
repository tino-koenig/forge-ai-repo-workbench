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
from core.run_reference import RunReferenceError, resolve_from_run_payload


@dataclass
class Evidence:
    path: Path
    line: int
    text: str


@dataclass
class InferencePoint:
    inference_id: str
    inference: str
    evidence_ids: list[str]
    rationale: str
    confidence: str


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


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    view = resolve_view(args)
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
    raw_target = request.payload.strip()

    target = resolve_file_or_symbol_target(repo_root, raw_target, session)

    if target is None:
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
            sections={"role_classification": None, "related_files": []},
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
    evidence_facts = build_evidence_facts(repo_root, evidence)
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
    sections = {
        "role_classification": {"role": role, "reason": rationale},
        "related_files": [str(path) for path in related],
        "resolved_target": str(rel_target),
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
    }
    if role_hypothesis_alternatives:
        sections["role_hypothesis_alternatives"] = role_hypothesis_alternatives
    if from_run_meta:
        sections.update(from_run_meta)
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
