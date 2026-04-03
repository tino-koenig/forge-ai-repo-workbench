from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import (
    ResolvedTarget,
    collect_line_evidence as collect_line_evidence_shared,
    find_related_files,
    load_index_path_class_map,
    prioritize_paths_by_index,
    resolve_file_or_symbol_target,
)
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import maybe_refine_summary, provenance_section, resolve_settings
from core.output_contracts import build_contract, emit_contract_json
from core.repo_io import read_text_file


SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}


@dataclass
class FindingEvidence:
    path: Path
    line: int
    text: str


@dataclass
class Finding:
    title: str
    severity: str
    explanation: str
    evidence: list[FindingEvidence]
    recommendation: str | None = None


def maybe_add(
    findings: list[Finding],
    *,
    condition: bool,
    title: str,
    severity: str,
    explanation: str,
    evidence: list[FindingEvidence],
    recommendation: str | None = None,
) -> None:
    if condition and evidence:
        findings.append(
            Finding(
                title=title,
                severity=severity,
                explanation=explanation,
                evidence=evidence,
                recommendation=recommendation,
            )
        )


def collect_line_evidence(path: Path, content: str, pattern: re.Pattern[str], limit: int = 4) -> list[FindingEvidence]:
    items = collect_line_evidence_shared(path, content, pattern, limit=limit)
    return [FindingEvidence(path=item.path, line=item.line, text=item.text) for item in items]


def detect_large_file(target: ResolvedTarget) -> Finding | None:
    line_count = len(target.content.splitlines())
    if line_count < 350:
        return None
    severity = "high" if line_count >= 700 else "medium"
    evidence = [FindingEvidence(path=target.path, line=1, text=f"file has {line_count} lines")]
    return Finding(
        title="Large File Complexity",
        severity=severity,
        explanation="Very large files are harder to review, test, and evolve safely.",
        evidence=evidence,
        recommendation="Split the file into focused modules with clearer responsibilities.",
    )


def detect_controller_overreach(target: ResolvedTarget) -> list[Finding]:
    findings: list[Finding] = []
    lower_path = str(target.path).lower()
    is_controller = "controller" in lower_path
    if not is_controller:
        return findings

    sql_pattern = re.compile(r"\b(select|insert|update|delete)\b", re.IGNORECASE)
    direct_sql = collect_line_evidence(target.path, target.content, sql_pattern)
    maybe_add(
        findings,
        condition=bool(direct_sql),
        title="Controller Overreach: Direct Query Logic",
        severity="high",
        explanation="Controller code appears to contain direct SQL concerns.",
        evidence=direct_sql,
        recommendation="Move query/data access logic into repository/service layers.",
    )

    business_pattern = re.compile(r"\b(calculate|price|discount|tax|validate|normalize)\b", re.IGNORECASE)
    business_logic = collect_line_evidence(target.path, target.content, business_pattern)
    maybe_add(
        findings,
        condition=len(business_logic) >= 3,
        title="Controller Overreach: Business Logic Density",
        severity="medium",
        explanation="Controller file contains multiple business-logic-like operations.",
        evidence=business_logic,
        recommendation="Extract business rules to service/domain components.",
    )
    return findings


def detect_missing_guards(target: ResolvedTarget) -> Finding | None:
    content = target.content
    route_like = re.search(r"(@app\.|@router\.|@route|def (get|post|put|delete)_)", content)
    if not route_like:
        return None

    guard_pattern = re.compile(r"\b(auth|authorize|permission|guard|require_login|is_admin)\b", re.IGNORECASE)
    guard_evidence = collect_line_evidence(target.path, content, guard_pattern, limit=2)
    if guard_evidence:
        return None

    endpoint_pattern = re.compile(r"^\s*def\s+\w+\(", re.IGNORECASE)
    endpoint_evidence = collect_line_evidence(target.path, content, endpoint_pattern, limit=3)
    if not endpoint_evidence:
        return None
    return Finding(
        title="Likely Missing Guard Checks",
        severity="medium",
        explanation="Endpoint-like code found without obvious guard/auth keywords.",
        evidence=endpoint_evidence,
        recommendation="Confirm authorization checks are enforced in middleware or decorators.",
    )


def detect_layer_query_mismatch(target: ResolvedTarget) -> Finding | None:
    path_lower = str(target.path).lower()
    if "controller" not in path_lower and "handler" not in path_lower:
        return None
    db_call_pattern = re.compile(r"\b(execute|fetchall|fetchone|raw|cursor)\b", re.IGNORECASE)
    evidence = collect_line_evidence(target.path, target.content, db_call_pattern, limit=4)
    if not evidence:
        return None
    return Finding(
        title="Direct Data Access in Outer Layer",
        severity="high",
        explanation="Outer-layer module appears to perform direct data access operations.",
        evidence=evidence,
        recommendation="Delegate DB calls to repository/data modules.",
    )


def detect_visible_antipatterns(target: ResolvedTarget, profile: Profile) -> list[Finding]:
    findings: list[Finding] = []

    todo_pattern = re.compile(r"^\s*(#|//|/\*)\s*.*\b(TODO|FIXME|HACK)\b", re.IGNORECASE)
    todo_evidence = collect_line_evidence(target.path, target.content, todo_pattern, limit=6)
    maybe_add(
        findings,
        condition=bool(todo_evidence),
        title="Pending Technical Debt Markers",
        severity="low",
        explanation="The target contains TODO/FIXME/HACK markers that may hide unfinished behavior.",
        evidence=todo_evidence,
        recommendation="Track and resolve critical markers via issues/tasks.",
    )

    bare_except = collect_line_evidence(target.path, target.content, re.compile(r"^\s*except\s*:\s*$"), limit=3)
    maybe_add(
        findings,
        condition=bool(bare_except),
        title="Bare Except Block",
        severity="medium",
        explanation="Bare exception handling can hide unexpected failures.",
        evidence=bare_except,
        recommendation="Catch specific exceptions and log failure context.",
    )

    if profile == Profile.DETAILED:
        print_calls = []
        print_pattern = re.compile(r"\bprint\(")
        for idx, line in enumerate(target.content.splitlines(), start=1):
            if not print_pattern.search(line):
                continue
            lowered = line.lower()
            if "debug" not in lowered and "trace" not in lowered:
                continue
            print_calls.append(FindingEvidence(path=target.path, line=idx, text=line.strip()))
            if len(print_calls) >= 4:
                break
        maybe_add(
            findings,
            condition=bool(print_calls),
            title="Debug Print Statements in Source",
            severity="low",
            explanation="Debug prints can leak noisy output and should usually be structured logging.",
            evidence=print_calls,
            recommendation="Replace debug prints with project logging conventions.",
        )

    return findings


def detect_inline_styles(target: ResolvedTarget) -> Finding | None:
    style_pattern = re.compile(r"\bstyle\s*=\s*['\"{]", re.IGNORECASE)
    evidence = collect_line_evidence(target.path, target.content, style_pattern, limit=4)
    if not evidence:
        return None
    return Finding(
        title="Inline Styles Detected",
        severity="low",
        explanation="Inline style usage can make styling harder to maintain at scale.",
        evidence=evidence,
        recommendation="Prefer shared style classes/components where possible.",
    )


def gather_related_targets(
    repo_root: Path,
    primary: ResolvedTarget,
    session: ExecutionSession,
    limit: int,
    path_classes: dict[str, str],
) -> list[ResolvedTarget]:
    primary_rel = primary.path.relative_to(repo_root)
    related: list[ResolvedTarget] = []

    related_rel = find_related_files(repo_root, primary_rel, session, limit=max(10, limit * 3))
    related_abs = [repo_root / rel for rel in related_rel]
    prioritized = prioritize_paths_by_index(
        repo_root,
        related_abs,
        path_classes,
        exclude_non_index_participating=True,
    )
    if not prioritized:
        prioritized = related_abs

    for path in prioritized[:limit]:
        content = read_text_file(path, session)
        if content is None:
            continue
        related.append(ResolvedTarget(path=path, content=content, source="related", kind="file"))
    return related


def review_target(target: ResolvedTarget, profile: Profile) -> list[Finding]:
    findings: list[Finding] = []

    large_file = detect_large_file(target)
    if large_file:
        findings.append(large_file)

    findings.extend(detect_controller_overreach(target))

    missing_guards = detect_missing_guards(target)
    if missing_guards:
        findings.append(missing_guards)

    layer_mismatch = detect_layer_query_mismatch(target)
    if layer_mismatch:
        findings.append(layer_mismatch)

    findings.extend(detect_visible_antipatterns(target, profile))

    inline_style = detect_inline_styles(target)
    if inline_style:
        findings.append(inline_style)

    findings.sort(
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity, 0),
            len(f.evidence),
        ),
        reverse=True,
    )
    return findings


def print_findings(repo_root: Path, findings: list[Finding]) -> None:
    if not findings:
        print("\n--- Findings ---")
        print("No concrete findings from active heuristics.")
        return

    print("\n--- Findings ---")
    for idx, finding in enumerate(findings, start=1):
        print(f"{idx}. {finding.title} [{finding.severity}]")
        print(f"   Explanation: {finding.explanation}")
        print("   Evidence:")
        for item in finding.evidence:
            rel = item.path.relative_to(repo_root)
            print(f"   - {rel}:{item.line}: {item.text}")
        if finding.recommendation:
            print(f"   Recommendation: {finding.recommendation}")


def print_summary(target: ResolvedTarget, findings: list[Finding], related_count: int) -> None:
    high = sum(1 for f in findings if f.severity == "high")
    medium = sum(1 for f in findings if f.severity == "medium")
    low = sum(1 for f in findings if f.severity == "low")
    print("\n--- Summary ---")
    print(
        f"Findings: {len(findings)} "
        f"(high={high}, medium={medium}, low={low}); related files reviewed={related_count}."
    )
    print(f"Target source: {target.source}")


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    target = resolve_file_or_symbol_target(repo_root, request.payload, session)
    path_classes: dict[str, str] = {}
    is_json = args.output_format == "json"

    if not is_json:
        print("=== FORGE REVIEW ===")
        print(f"Profile: {request.profile.value}")
        print(f"Target: {request.payload}")
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        path_classes = load_index_path_class_map(repo_root, session)
        if not is_json:
            if path_classes:
                print("Index: loaded .forge/index.json")
            else:
                print("Index: not available, using direct repository scan only")

    if target is None:
        summary = "Target could not be resolved to a readable file or symbol."
        uncertainty = [
            "no matching file path under repo root",
            "no symbol-like match found in readable text files",
        ]
        next_step = 'Run: forge query "where is the relevant logic implemented?"'
        if is_json:
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary=summary,
                evidence=[],
                uncertainty=uncertainty,
                next_step=next_step,
                sections={"findings": []},
            )
            emit_contract_json(contract)
            return 0
        print("\n--- Findings ---")
        print(summary)
        print("\n--- Uncertainty ---")
        for note in uncertainty:
            print(f"- {note}")
        print("\n--- Next Step ---")
        print(next_step)
        return 0

    primary_findings = review_target(target, request.profile)
    all_findings = list(primary_findings)
    related_count = 0

    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        related_limit = 1 if request.profile == Profile.STANDARD else 3
        related_targets = gather_related_targets(
            repo_root,
            target,
            session,
            limit=related_limit,
            path_classes=path_classes,
        )
        related_count = len(related_targets)
        for related in related_targets:
            all_findings.extend(review_target(related, request.profile))

    all_findings.sort(
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 0), len(f.evidence)),
        reverse=True,
    )
    max_findings = 6 if request.profile == Profile.SIMPLE else 10 if request.profile == Profile.STANDARD else 15
    capped_findings = all_findings[:max_findings]
    uncertainty = [
        "Review findings are heuristic and may miss context outside scanned files.",
    ]
    next_step = (
        f"Inspect: {capped_findings[0].evidence[0].path.relative_to(repo_root)}:{capped_findings[0].evidence[0].line}"
        if capped_findings
        else f"Run: forge explain {target.path.relative_to(repo_root)}"
    )
    evidence_payload: list[dict[str, object]] = []
    findings_payload: list[dict[str, object]] = []
    for finding in capped_findings:
        item = {
            "title": finding.title,
            "severity": finding.severity,
            "explanation": finding.explanation,
            "recommendation": finding.recommendation,
            "evidence": [
                {
                    "path": str(e.path.relative_to(repo_root)),
                    "line": e.line,
                    "text": e.text,
                }
                for e in finding.evidence
            ],
        }
        findings_payload.append(item)
        evidence_payload.extend(item["evidence"])
    if is_json:
        high = sum(1 for f in capped_findings if f.severity == "high")
        medium = sum(1 for f in capped_findings if f.severity == "medium")
        low = sum(1 for f in capped_findings if f.severity == "low")
        summary = (
            f"Findings: {len(capped_findings)} "
            f"(high={high}, medium={medium}, low={low}); related files reviewed={related_count}."
        )
        llm_settings = resolve_settings(args)
        llm_outcome = maybe_refine_summary(
            capability=request.capability,
            profile=request.profile,
            task=request.payload,
            deterministic_summary=summary,
            evidence=evidence_payload,
            settings=llm_settings,
        )
        summary = llm_outcome.summary
        uncertainty.extend(llm_outcome.uncertainty_notes)
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=evidence_payload,
            uncertainty=uncertainty,
            next_step=next_step,
            sections={
                "findings": findings_payload,
                "target_source": target.source,
                "llm_usage": llm_outcome.usage,
                "provenance": provenance_section(
                    llm_used=bool(llm_outcome.usage.get("used")),
                    evidence_count=len(evidence_payload),
                ),
            },
        )
        emit_contract_json(contract)
        return 0

    high = sum(1 for f in capped_findings if f.severity == "high")
    medium = sum(1 for f in capped_findings if f.severity == "medium")
    low = sum(1 for f in capped_findings if f.severity == "low")
    summary = (
        f"Findings: {len(capped_findings)} "
        f"(high={high}, medium={medium}, low={low}); related files reviewed={related_count}."
    )
    llm_settings = resolve_settings(args)
    llm_outcome = maybe_refine_summary(
        capability=request.capability,
        profile=request.profile,
        task=request.payload,
        deterministic_summary=summary,
        evidence=evidence_payload,
        settings=llm_settings,
    )
    uncertainty.extend(llm_outcome.uncertainty_notes)

    print_summary(target, capped_findings, related_count)
    print("\n--- Refined Summary ---")
    print(llm_outcome.summary)
    print_findings(repo_root, capped_findings)
    print("\n--- LLM Usage ---")
    print(f"Policy: {llm_outcome.usage['policy']}")
    print(f"Mode: {llm_outcome.usage['mode']}")
    print(f"Used: {llm_outcome.usage['used']}")
    print(f"Provider: {llm_outcome.usage['provider'] or 'none'}")
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
    for note in uncertainty:
        print(f"- {note}")
    print("\n--- Next Step ---")
    print(next_step)

    return 0
