from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import (
    RelatedTarget,
    ResolvedTarget,
    collect_line_evidence as collect_line_evidence_shared,
    is_path_like_target,
    load_index_path_class_map,
    prioritize_paths_by_index,
    rank_related_targets,
    resolve_file_target,
    resolve_file_or_symbol_target,
)
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import maybe_refine_summary, provenance_section, resolve_settings
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.review_rules import ReviewRule, load_review_rules
from core.repo_io import read_text_file
from core.run_reference import RunReferenceError, resolve_from_run_payload


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
    rule_id: str | None = None


@dataclass(frozen=True)
class ReviewPolicy:
    large_file_medium_threshold: int
    large_file_high_threshold: int
    findings_max_items: int
    related_max_targets: int
    evidence_max_per_finding: int


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


def _resolve_runtime_int(args, key: str, default: int, *, min_value: int = 1, max_value: int = 20000) -> tuple[int, str]:
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


def _cap_finding_evidence(findings: list[Finding], max_items: int) -> list[Finding]:
    for finding in findings:
        finding.evidence = finding.evidence[:max_items]
    return findings


def detect_large_file(target: ResolvedTarget, policy: ReviewPolicy) -> Finding | None:
    line_count = len(target.content.splitlines())
    if line_count < policy.large_file_medium_threshold:
        return None
    severity = "high" if line_count >= policy.large_file_high_threshold else "medium"
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


def _path_allowed(path: Path, rule: ReviewRule) -> bool:
    lowered = str(path).lower()
    if rule.path_includes and not any(token.lower() in lowered for token in rule.path_includes):
        return False
    if rule.path_excludes and any(token.lower() in lowered for token in rule.path_excludes):
        return False
    return True


def apply_external_rules(target: ResolvedTarget, rules: list[ReviewRule]) -> list[Finding]:
    findings: list[Finding] = []
    for rule in rules:
        if not _path_allowed(target.path, rule):
            continue
        evidence = collect_line_evidence(target.path, target.content, rule.regex, limit=5)
        if not evidence:
            continue
        findings.append(
            Finding(
                title=rule.title,
                severity=rule.severity,
                explanation=rule.explanation,
                evidence=evidence,
                recommendation=rule.recommendation,
                rule_id=rule.rule_id,
            )
        )
    return findings


def gather_related_targets(
    repo_root: Path,
    primary: ResolvedTarget,
    session: ExecutionSession,
    limit: int,
    path_classes: dict[str, str],
) -> tuple[list[ResolvedTarget], list[RelatedTarget]]:
    primary_rel = primary.path.relative_to(repo_root)
    related: list[ResolvedTarget] = []
    ranked_related = rank_related_targets(
        repo_root,
        primary_rel,
        session,
        path_classes,
        limit=max(10, limit * 3),
    )
    related_abs = [repo_root / item.path for item in ranked_related]
    prioritized = prioritize_paths_by_index(
        repo_root,
        related_abs,
        path_classes,
        exclude_non_index_participating=True,
    )
    if not prioritized:
        prioritized = related_abs
    ranked_map = {repo_root / item.path: item for item in ranked_related}
    selected_ranked: list[RelatedTarget] = []

    for path in prioritized[:limit]:
        content = read_text_file(path, session)
        if content is None:
            continue
        related.append(ResolvedTarget(path=path, content=content, source="related", kind="file"))
        ranked = ranked_map.get(path)
        if ranked is not None:
            selected_ranked.append(ranked)
    return related, selected_ranked


def review_target(target: ResolvedTarget, profile: Profile, external_rules: list[ReviewRule], policy: ReviewPolicy) -> list[Finding]:
    findings: list[Finding] = []

    large_file = detect_large_file(target, policy)
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

    findings.extend(apply_external_rules(target, external_rules))
    _cap_finding_evidence(findings, policy.evidence_max_per_finding)

    findings.sort(
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity, 0),
            len(f.evidence),
        ),
        reverse=True,
    )
    return findings


def print_findings(repo_root: Path, findings: list[Finding], view: str) -> None:
    if not findings:
        print("\n--- Findings ---")
        print("No concrete findings from active heuristics.")
        return

    print("\n--- Findings ---")
    finding_limit = 1 if is_compact(view) else 3 if view == "standard" else len(findings)
    for idx, finding in enumerate(findings[:finding_limit], start=1):
        print(f"{idx}. {finding.title} [{finding.severity}]")
        if finding.rule_id and not is_compact(view):
            print(f"   Rule: {finding.rule_id}")
        print(f"   Explanation: {finding.explanation}")
        print("   Evidence:")
        ev_limit = 1 if is_compact(view) else 2 if view == "standard" else len(finding.evidence)
        for item in finding.evidence[:ev_limit]:
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
    path_like_target = is_path_like_target(request.payload)
    target = (
        resolve_file_target(repo_root, request.payload, session)
        if path_like_target
        else resolve_file_or_symbol_target(repo_root, request.payload, session)
    )
    external_rules, rule_errors = load_review_rules(repo_root)
    path_classes: dict[str, str] = {}
    is_json = args.output_format == "json"
    view = resolve_view(args)

    if not is_json:
        print("=== FORGE REVIEW ===")
        print(f"Profile: {request.profile.value}")
        print(f"Target: {request.payload}")
        if is_full(view) and rule_errors:
            print("Review rules: invalid entries detected; invalid rules were skipped")
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        path_classes = load_index_path_class_map(repo_root, session)
        if not is_json:
            if path_classes:
                print("Index: loaded .forge/index.json")
            else:
                print("Index: not available, using direct repository scan only")

    large_file_medium_threshold, large_file_medium_source = _resolve_runtime_int(
        args,
        "review.large_file.medium_threshold",
        350,
        min_value=1,
        max_value=100000,
    )
    large_file_high_threshold, large_file_high_source = _resolve_runtime_int(
        args,
        "review.large_file.high_threshold",
        700,
        min_value=1,
        max_value=100000,
    )
    if large_file_high_threshold < large_file_medium_threshold:
        large_file_high_threshold = large_file_medium_threshold
        large_file_high_source = "default"
    findings_max_items, findings_max_source = _resolve_runtime_int(
        args,
        "review.findings.max_items",
        15,
        min_value=1,
        max_value=200,
    )
    related_max_targets, related_max_source = _resolve_runtime_int(
        args,
        "review.related.max_targets",
        3,
        min_value=1,
        max_value=50,
    )
    evidence_max_per_finding, evidence_max_source = _resolve_runtime_int(
        args,
        "review.evidence.max_per_finding",
        6,
        min_value=1,
        max_value=50,
    )
    review_policy = ReviewPolicy(
        large_file_medium_threshold=large_file_medium_threshold,
        large_file_high_threshold=large_file_high_threshold,
        findings_max_items=findings_max_items,
        related_max_targets=related_max_targets,
        evidence_max_per_finding=evidence_max_per_finding,
    )
    review_policy_section = {
        "values": {
            "large_file_medium_threshold": review_policy.large_file_medium_threshold,
            "large_file_high_threshold": review_policy.large_file_high_threshold,
            "findings_max_items": review_policy.findings_max_items,
            "related_max_targets": review_policy.related_max_targets,
            "evidence_max_per_finding": review_policy.evidence_max_per_finding,
        },
        "sources": {
            "large_file_medium_threshold": large_file_medium_source,
            "large_file_high_threshold": large_file_high_source,
            "findings_max_items": findings_max_source,
            "related_max_targets": related_max_source,
            "evidence_max_per_finding": evidence_max_source,
        },
    }

    if target is None:
        if path_like_target:
            summary = "Target path could not be resolved to a readable repository file."
            uncertainty = [
                "path-like target did not resolve to a readable file under repo root",
                "symbol fallback was skipped intentionally for path-like inputs",
            ]
        else:
            summary = "Target could not be resolved to a readable file or symbol."
            uncertainty = [
                "no matching file path under repo root",
                "no symbol-like match found in readable text files",
            ]
        next_step = 'Run: forge query "where is the relevant logic implemented?"'
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=[],
            uncertainty=uncertainty,
            next_step=next_step,
            sections={
                "findings": [],
                "related_targets": [],
                "review_policy": review_policy_section,
                "review_rules": {"loaded": len(external_rules), "errors": rule_errors},
            },
        )
        if is_json:
            if from_run_meta:
                contract["sections"].update(from_run_meta)
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

    primary_findings = review_target(target, request.profile, external_rules, review_policy)
    all_findings = list(primary_findings)
    related_count = 0
    related_target_meta: list[dict[str, object]] = []

    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        related_limit = 1 if request.profile == Profile.STANDARD else 3
        related_limit = min(related_limit, review_policy.related_max_targets)
        related_targets, related_ranked = gather_related_targets(
            repo_root,
            target,
            session,
            limit=related_limit,
            path_classes=path_classes,
        )
        related_count = len(related_targets)
        related_target_meta = [
            {
                "path": str(item.path),
                "score": item.score,
                "rationale": item.rationale,
            }
            for item in related_ranked
        ]
        for related in related_targets:
            all_findings.extend(review_target(related, request.profile, external_rules, review_policy))

    all_findings.sort(
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 0), len(f.evidence)),
        reverse=True,
    )
    profile_max_findings = 6 if request.profile == Profile.SIMPLE else 10 if request.profile == Profile.STANDARD else 15
    max_findings = min(profile_max_findings, review_policy.findings_max_items)
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
            "rule_id": finding.rule_id,
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
    high = sum(1 for f in capped_findings if f.severity == "high")
    medium = sum(1 for f in capped_findings if f.severity == "medium")
    low = sum(1 for f in capped_findings if f.severity == "low")
    deterministic_summary = (
        f"Findings: {len(capped_findings)} "
        f"(high={high}, medium={medium}, low={low}); related files reviewed={related_count}."
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
            "related_targets": related_target_meta,
            "review_policy": review_policy_section,
            "review_rules": {"loaded": len(external_rules), "errors": rule_errors},
            "llm_usage": llm_outcome.usage,
            "provenance": provenance_section(
                llm_used=bool(llm_outcome.usage.get("used")),
                evidence_count=len(evidence_payload),
            ),
        },
    )
    if from_run_meta:
        contract["sections"].update(from_run_meta)
    if is_json:
        emit_contract_json(contract)
        return 0

    if is_full(view):
        print_summary(target, capped_findings, related_count)
    print("\n--- Answer ---")
    print(llm_outcome.summary)
    print_findings(repo_root, capped_findings, view)
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
    print("\n--- Uncertainty ---")
    notes = uncertainty if is_full(view) else uncertainty[:1]
    for note in notes:
        print(f"- {note}")
    if is_full(view):
        print("\n--- Review Rules ---")
        print(f"Loaded rules: {len(external_rules)}")
        if rule_errors:
            print("Errors:")
            for item in rule_errors[:6]:
                print(f"- {item}")
    print("\n--- Next Step ---")
    print(next_step)

    return 0
