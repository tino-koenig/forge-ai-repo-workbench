#!/usr/bin/env python3
"""Capability quality gates for Forge."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORGE = ROOT / "forge.py"
FIXTURE_SRC = ROOT / "tests" / "fixtures" / "basic_repo"


class GateError(RuntimeError):
    pass


def run_cmd(args: list[str], cwd: Path, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if expect_ok and proc.returncode != 0:
        raise GateError(
            f"Command failed ({proc.returncode}): {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def parse_json_output(output: str) -> dict:
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise GateError(f"Expected JSON output but parsing failed: {exc}\nOutput:\n{output}") from exc


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def snapshot_repo_files(repo_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if rel.parts and rel.parts[0] == ".forge":
            continue
        snapshot[str(rel)] = file_hash(path)
    return snapshot


def ensure_output_contract(payload: dict, capability: str) -> None:
    for field in ("capability", "profile", "summary", "evidence", "uncertainty", "next_step"):
        assert_true(field in payload, f"{capability}: missing contract field '{field}'")
    assert_true(payload["capability"] == capability, f"{capability}: capability mismatch in JSON contract")
    assert_true(isinstance(payload["evidence"], list), f"{capability}: evidence must be a list")
    assert_true(isinstance(payload["uncertainty"], list), f"{capability}: uncertainty must be a list")


def gate_behavior_smoke(repo_root: Path) -> None:
    commands = [
        ["python3", str(FORGE), "--repo-root", str(repo_root), "index"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "query", "where", "is", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "explain", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "review", "src/controller.py"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "describe"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "test", "src/service.py"],
    ]
    for cmd in commands:
        run_cmd(cmd, cwd=ROOT)


def gate_output_contract(repo_root: Path) -> None:
    query_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "query", "compute_price"],
        cwd=ROOT,
    ).stdout
    explain_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "explain", "compute_price"],
        cwd=ROOT,
    ).stdout
    review_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "review", "src/controller.py"],
        cwd=ROOT,
    ).stdout

    query_payload = parse_json_output(query_out)
    explain_payload = parse_json_output(explain_out)
    review_payload = parse_json_output(review_out)

    ensure_output_contract(query_payload, "query")
    ensure_output_contract(explain_payload, "explain")
    ensure_output_contract(review_payload, "review")


def gate_llm_path(repo_root: Path) -> None:
    query_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    explain_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "explain",
                "detailed",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    review_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "review",
                "detailed",
                "src/controller.py",
            ],
            cwd=ROOT,
        ).stdout
    )

    for capability, payload in (
        ("query", query_payload),
        ("explain", explain_payload),
        ("review", review_payload),
    ):
        sections = payload.get("sections", {})
        llm_usage = sections.get("llm_usage", {})
        assert_true(bool(llm_usage), f"{capability}: expected llm_usage section")
        assert_true(llm_usage.get("used") is True, f"{capability}: expected LLM to be used with mock provider")
        provenance = sections.get("provenance", {})
        assert_true(bool(provenance), f"{capability}: expected provenance section")
        assert_true(
            provenance.get("inference_source") == "deterministic_heuristics+llm",
            f"{capability}: expected llm inference provenance marker",
        )


def gate_evidence_quality(repo_root: Path) -> None:
    query_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "query", "compute_price"],
            cwd=ROOT,
        ).stdout
    )
    explain_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "explain", "compute_price"],
            cwd=ROOT,
        ).stdout
    )
    review_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "review", "src/controller.py"],
            cwd=ROOT,
        ).stdout
    )

    assert_true(len(query_payload["evidence"]) > 0, "query: expected non-empty evidence")
    assert_true(len(explain_payload["evidence"]) > 0, "explain: expected non-empty evidence")
    findings = review_payload.get("sections", {}).get("findings", [])
    assert_true(len(findings) > 0, "review: expected at least one finding on controller fixture")
    first_evidence = findings[0].get("evidence", [])
    assert_true(len(first_evidence) > 0, "review: finding must include evidence")


def gate_effect_boundaries(repo_root: Path) -> None:
    before = snapshot_repo_files(repo_root)
    read_only_commands = [
        ["python3", str(FORGE), "--repo-root", str(repo_root), "query", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "explain", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "review", "src/controller.py"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "describe"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "test", "src/service.py"],
    ]
    for cmd in read_only_commands:
        run_cmd(cmd, cwd=ROOT)
    after = snapshot_repo_files(repo_root)
    assert_true(before == after, "read-only capabilities changed repository files outside .forge/")


def gate_fallback_with_and_without_index(repo_root: Path) -> None:
    # Ensure index exists first.
    run_cmd(["python3", str(FORGE), "--repo-root", str(repo_root), "index"], cwd=ROOT)
    with_index = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "query", "compute_price"],
        cwd=ROOT,
    ).stdout
    assert_true("Index: loaded .forge/index.json" in with_index, "query: expected index-assisted mode")

    shutil.rmtree(repo_root / ".forge", ignore_errors=True)

    without_index_checks = [
        ["query", "compute_price"],
        ["explain", "detailed", "compute_price"],
        ["review", "detailed", "src/controller.py"],
        ["describe", "detailed"],
        ["test", "detailed", "src/service.py"],
    ]
    for parts in without_index_checks:
        cmd = ["python3", str(FORGE), "--repo-root", str(repo_root), *parts]
        out = run_cmd(cmd, cwd=ROOT).stdout
        assert_true("Index: not available" in out or "Index: skipped" in out, f"{parts[0]}: expected index fallback message")


def run_all_gates() -> None:
    with tempfile.TemporaryDirectory(prefix="forge-gates-") as temp_dir:
        temp_repo = Path(temp_dir) / "repo"
        shutil.copytree(FIXTURE_SRC, temp_repo)

        gate_behavior_smoke(temp_repo)
        gate_output_contract(temp_repo)
        gate_llm_path(temp_repo)
        gate_evidence_quality(temp_repo)
        gate_effect_boundaries(temp_repo)
        gate_fallback_with_and_without_index(temp_repo)


def main() -> int:
    try:
        run_all_gates()
    except GateError as exc:
        print(f"[quality-gates] FAILED: {exc}")
        return 1
    print("[quality-gates] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
