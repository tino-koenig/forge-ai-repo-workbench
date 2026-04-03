from __future__ import annotations

import re
import shlex
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from core.analysis_primitives import ResolvedTarget, resolve_file_or_symbol_target
from core.analysis_primitives import load_index_path_class_map, prioritize_paths_by_index
from core.capability_model import CommandRequest, Profile
from core.effects import ExecutionSession
from core.llm_integration import maybe_refine_summary, resolve_settings
from core.llm_integration import provenance_section
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_compact, is_full, resolve_view
from core.repo_io import iter_repo_files, read_text_file
from core.run_reference import RunReferenceError, resolve_from_run_payload


@dataclass
class TestConventions:
    framework: str
    naming_style: str
    assertion_style: str
    likely_test_dir: str


def parse_payload(payload: str) -> tuple[str, list[str]]:
    tokens = shlex.split(payload)
    target_tokens: list[str] = []
    explicit_cases: list[str] = []

    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token in {"--case", "-c"}:
            idx += 1
            case_parts: list[str] = []
            while idx < len(tokens) and tokens[idx] not in {"--case", "-c"} and not tokens[idx].startswith("--case="):
                case_parts.append(tokens[idx])
                idx += 1
            if case_parts:
                explicit_cases.append(" ".join(case_parts))
            continue
        if token.startswith("--case="):
            explicit_cases.append(token.split("=", 1)[1])
            idx += 1
            continue
        target_tokens.append(token)
        idx += 1

    raw_target = " ".join(target_tokens).strip() if target_tokens else payload.strip()
    inline = re.findall(r"(?:case:|edge case:)\s*([^\n,;]+)", payload, re.IGNORECASE)
    explicit_cases.extend([item.strip() for item in inline if item.strip()])
    # Dedupe preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for case in explicit_cases:
        if case in seen:
            continue
        seen.add(case)
        deduped.append(case)
    return raw_target, deduped


def find_test_files(
    repo_root: Path,
    session: ExecutionSession,
    path_classes: dict[str, str],
) -> list[Path]:
    tests: list[Path] = []
    for path in iter_repo_files(repo_root, session):
        rel = path.relative_to(repo_root)
        name = rel.name.lower()
        in_test_dir = rel.parts and rel.parts[0].lower() in {"test", "tests"}
        named_as_test = name.startswith("test_") or name.endswith("_test.py")
        if in_test_dir or named_as_test:
            tests.append(path)
    prioritized = prioritize_paths_by_index(
        repo_root,
        tests,
        path_classes,
        exclude_non_index_participating=False,
    )
    return prioritized if prioritized else tests


def detect_conventions(
    repo_root: Path,
    session: ExecutionSession,
    path_classes: dict[str, str],
) -> TestConventions:
    test_files = find_test_files(repo_root, session, path_classes)
    if not test_files:
        return TestConventions(
            framework="pytest",
            naming_style="test_<unit>.py",
            assertion_style="assert",
            likely_test_dir="tests/",
        )

    framework_counter: Counter[str] = Counter()
    naming_counter: Counter[str] = Counter()
    assertion_counter: Counter[str] = Counter()
    directory_counter: Counter[str] = Counter()

    for path in test_files[:80]:
        rel = path.relative_to(repo_root)
        name = rel.name
        content = read_text_file(path, session) or ""
        directory_counter[str(rel.parent)] += 1

        if name.startswith("test_"):
            naming_counter["test_<unit>.py"] += 1
        if name.endswith("_test.py"):
            naming_counter["<unit>_test.py"] += 1

        if re.search(r"^\s*import\s+pytest|^\s*from\s+pytest\s+import", content, re.MULTILINE):
            framework_counter["pytest"] += 1
        if re.search(r"^\s*import\s+unittest|^\s*from\s+unittest\s+import", content, re.MULTILINE):
            framework_counter["unittest"] += 1

        if "self.assert" in content:
            assertion_counter["self.assert*"] += 1
        if re.search(r"^\s*assert\s+", content, re.MULTILINE):
            assertion_counter["assert"] += 1

    framework = framework_counter.most_common(1)[0][0] if framework_counter else "pytest"
    naming_style = naming_counter.most_common(1)[0][0] if naming_counter else "test_<unit>.py"
    assertion_style = assertion_counter.most_common(1)[0][0] if assertion_counter else "assert"
    likely_test_dir = directory_counter.most_common(1)[0][0] if directory_counter else "tests"
    if likely_test_dir == ".":
        likely_test_dir = "tests"

    return TestConventions(
        framework=framework,
        naming_style=naming_style,
        assertion_style=assertion_style,
        likely_test_dir=f"{likely_test_dir}/" if not likely_test_dir.endswith("/") else likely_test_dir,
    )


def likely_test_path(repo_root: Path, target: ResolvedTarget, conventions: TestConventions) -> str:
    rel = target.path.relative_to(repo_root)
    base = rel.stem
    test_dir = conventions.likely_test_dir.strip("/")
    if not test_dir:
        test_dir = "tests"
    if conventions.naming_style == "<unit>_test.py":
        file_name = f"{base}_test.py"
    else:
        file_name = f"test_{base}.py"
    return f"{test_dir}/{file_name}"


def extract_units(content: str, max_items: int) -> list[str]:
    units = re.findall(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE)
    deduped: list[str] = []
    seen: set[str] = set()
    for unit in units:
        if unit in seen:
            continue
        seen.add(unit)
        deduped.append(unit)
    return deduped[:max_items]


def derive_cases(target: ResolvedTarget, explicit_cases: list[str], profile: Profile) -> list[str]:
    cases: list[str] = []
    for item in explicit_cases:
        cases.append(f"requested: {item}")

    units = extract_units(target.content, max_items=6 if profile != Profile.SIMPLE else 3)
    if not units:
        units = [target.path.stem]

    for unit in units:
        cases.append(f"{unit}: happy path returns expected result")
        cases.append(f"{unit}: invalid input handling")

    if re.search(r"\braise\b|\bValueError\b|\bException\b", target.content):
        cases.append("error path: expected exception is raised with invalid state/input")
    if re.search(r"[<>]=?|==|!=|\bmin\b|\bmax\b|\bboundary\b", target.content):
        cases.append("boundary values: lower/upper threshold behavior")
    if re.search(r"\bNone\b|\bnull\b|\boptional\b", target.content, re.IGNORECASE):
        cases.append("null/None behavior for optional values")

    # Dedupe preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for case in cases:
        key = case.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(case)

    if profile == Profile.SIMPLE:
        return deduped[:6]
    if profile == Profile.STANDARD:
        return deduped[:10]
    return deduped[:14]


def build_draft_skeleton(
    target: ResolvedTarget,
    conventions: TestConventions,
    cases: list[str],
    profile: Profile,
) -> str:
    rel_name = target.path.stem
    test_names: list[str] = []
    for case in cases[: (3 if profile == Profile.STANDARD else 5)]:
        slug = re.sub(r"[^a-z0-9]+", "_", case.lower()).strip("_")
        test_names.append(f"test_{slug[:50]}")

    if conventions.framework == "unittest":
        pass_method = "    pass\n"
        methods = "\n".join(
            [
                f"    def {name}(self):\n"
                "        # Arrange\n"
                "        # Act\n"
                "        # Assert\n"
                "        self.fail('Implement test')\n"
                for name in test_names
            ]
        )
        return (
            "import unittest\n\n"
            f"class Test{rel_name.title().replace('_', '')}(unittest.TestCase):\n"
            f"{methods or pass_method}"
        )

    placeholder = "def test_placeholder():\n    assert False\n"
    body = "\n".join(
        [
            f"def {name}():\n"
            "    # Arrange\n"
            "    # Act\n"
            "    # Assert\n"
            "    assert False  # replace with real assertion\n"
            for name in test_names
        ]
    )
    return f"# Draft tests for {target.path.name}\n\n{body or placeholder}"


def collect_test_evidence(
    target: ResolvedTarget,
    repo_root: Path,
    cases: list[str],
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
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
        if len(evidence) >= 6:
            break
    for case in cases[:4]:
        evidence.append(
            {
                "path": str(target.path.relative_to(repo_root)),
                "line": 0,
                "text": f"proposed_case={case}",
            }
        )
    return evidence


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
        if args.output_format == "json":
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary="Run reference could not be resolved.",
                evidence=[],
                uncertainty=[str(exc)],
                next_step="Run: forge runs list",
                sections={"status": "from_run_resolution_failed"},
            )
            emit_contract_json(contract)
            return 1
        print(f"Run reference error: {exc}")
        return 1
    request = CommandRequest(capability=request.capability, profile=request.profile, payload=resolved_payload)
    raw_target, explicit_cases = parse_payload(request.payload)
    target = resolve_file_or_symbol_target(repo_root, raw_target, session)
    path_classes: dict[str, str] = {}
    is_json = args.output_format == "json"
    view = resolve_view(args)
    index_status: str | None = None

    if not is_json:
        print("=== FORGE TEST ===")
        print(f"Profile: {request.profile.value}")
        print(f"Target: {request.payload}")
        if explicit_cases:
            print(f"Explicit requested cases: {', '.join(explicit_cases)}")
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        path_classes = load_index_path_class_map(repo_root, session)
        if path_classes:
            index_status = "loaded .forge/index.json"
        else:
            index_status = "not available, using direct repository scan only"
        if not is_json:
            print(f"Index: {index_status}")

    if target is None:
        summary = "Target could not be resolved to a readable file or symbol."
        uncertainty = [
            "no matching file path under repo root",
            "no symbol-like match found in readable text files",
        ]
        next_step = 'Run: forge query "where is the relevant logic implemented?"'
        if is_json:
            sections: dict[str, object] = {"resolved_target": None, "proposed_cases": []}
            if index_status:
                sections["index_status"] = index_status
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary=summary,
                evidence=[],
                uncertainty=uncertainty,
                next_step=next_step,
                sections=sections,
            )
            if from_run_meta:
                contract["sections"].update(from_run_meta)
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

    conventions = detect_conventions(repo_root, session, path_classes)
    test_location = likely_test_path(repo_root, target, conventions)
    cases = derive_cases(target, explicit_cases, request.profile)
    resolved = target.path.relative_to(repo_root)
    deterministic_summary = f"Drafted test plan for {resolved} ({target.source})."
    evidence_payload = collect_test_evidence(target, repo_root, cases)
    llm_outcome = maybe_refine_summary(
        capability=request.capability,
        profile=request.profile,
        task=request.payload,
        deterministic_summary=deterministic_summary,
        evidence=evidence_payload,
        settings=resolve_settings(args, repo_root),
        repo_root=repo_root,
    )
    uncertainty = []
    if target.source == "symbol":
        uncertainty.append("Symbol target resolution is best-effort and may require manual confirmation.")
    else:
        uncertainty.append("Proposed test cases are heuristic and should be reviewed before implementation.")
    uncertainty.extend(llm_outcome.uncertainty_notes)
    next_step = f"Run: forge explain {resolved}"
    skeleton = None
    if request.profile in {Profile.STANDARD, Profile.DETAILED}:
        skeleton = build_draft_skeleton(target, conventions, cases, request.profile)
    sections: dict[str, object] = {
        "resolved_target": {"path": str(resolved), "source": target.source},
        "test_location": test_location,
        "conventions": {
            "framework": conventions.framework,
            "naming_style": conventions.naming_style,
            "assertion_style": conventions.assertion_style,
            "likely_test_dir": conventions.likely_test_dir,
        },
        "proposed_cases": cases,
    }
    if skeleton:
        sections["draft_skeleton"] = skeleton
    if index_status:
        sections["index_status"] = index_status
    if from_run_meta:
        sections.update(from_run_meta)
    sections["llm_usage"] = llm_outcome.usage
    sections["provenance"] = provenance_section(
        llm_used=bool(llm_outcome.usage.get("used")),
        evidence_count=len(evidence_payload),
    )

    if is_json:
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=llm_outcome.summary,
            evidence=evidence_payload,
            uncertainty=uncertainty,
            next_step=next_step,
            sections=sections,
        )
        emit_contract_json(contract)
        return 0

    print("\n--- Summary ---")
    print(llm_outcome.summary)

    print("\n--- Likely Test Location ---")
    print(test_location)

    print("\n--- Existing Test Conventions ---")
    print(f"Framework: {conventions.framework}")
    if is_full(view):
        print(f"Naming: {conventions.naming_style}")
        print(f"Assertions: {conventions.assertion_style}")
    print(f"Primary test dir: {conventions.likely_test_dir}")

    print("\n--- Proposed Test Cases ---")
    case_limit = 3 if is_compact(view) else 6 if view == "standard" else len(cases)
    for idx, case in enumerate(cases[:case_limit], start=1):
        print(f"{idx}. {case}")

    if skeleton and is_full(view):
        print("\n--- Draft Test Skeleton ---")
        print("```python")
        print(skeleton)
        print("```")

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

    print("\n--- Next Step ---")
    print(next_step)
    return 0
