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


def run_cmd(
    args: list[str],
    cwd: Path,
    expect_ok: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
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
        ["python3", str(FORGE), "--repo-root", str(repo_root), "doctor"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "config", "validate"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "query", "where", "is", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "explain", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "review", "src/controller.py"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "describe"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "test", "src/service.py"],
    ]
    for cmd in commands:
        run_cmd(cmd, cwd=ROOT)


def gate_output_contract(repo_root: Path) -> None:
    doctor_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "doctor"],
        cwd=ROOT,
    ).stdout
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
    describe_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "describe"],
        cwd=ROOT,
    ).stdout
    test_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "test", "src/service.py"],
        cwd=ROOT,
    ).stdout

    doctor_payload = parse_json_output(doctor_out)
    query_payload = parse_json_output(query_out)
    explain_payload = parse_json_output(explain_out)
    review_payload = parse_json_output(review_out)
    describe_payload = parse_json_output(describe_out)
    test_payload = parse_json_output(test_out)

    ensure_output_contract(doctor_payload, "doctor")
    ensure_output_contract(query_payload, "query")
    ensure_output_contract(explain_payload, "explain")
    ensure_output_contract(review_payload, "review")
    ensure_output_contract(describe_payload, "describe")
    ensure_output_contract(test_payload, "test")
    assert_true("sections" in describe_payload, "describe: expected sections payload")
    assert_true("sections" in test_payload, "test: expected sections payload")


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


def gate_openai_compatible_provider(repo_root: Path) -> None:
    env = os.environ.copy()
    env["FORGE_LLM_PROVIDER"] = "openai_compatible"
    env["FORGE_LLM_BASE_URL"] = "mock://openai/v1"
    env["FORGE_LLM_MODEL"] = "gpt-test"
    env["FORGE_LLM_API_KEY"] = "test-key"

    payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
            env=env,
        ).stdout
    )
    usage = payload.get("sections", {}).get("llm_usage", {})
    assert_true(usage.get("provider") == "openai_compatible", "expected openai_compatible provider")
    assert_true(usage.get("used") is True, "expected openai_compatible provider usage")
    assert_true(
        str(payload.get("summary", "")).startswith("Refined via openai_compatible provider"),
        "expected summary from openai-compatible completion",
    )


def gate_config_toml_fallback(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        (
            "[llm]\n"
            'provider = "openai_compatible"\n'
            "[llm.openai_compatible]\n"
            'base_url = "http://127.0.0.1:1/v1"\n'
            'model = "gpt-test"\n'
            'api_key_env = "FORGE_MISSING_KEY"\n'
            "timeout_s = 1\n"
        ),
        encoding="utf-8",
    )

    payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
            env=os.environ.copy(),
        ).stdout
    )
    usage = payload.get("sections", {}).get("llm_usage", {})
    assert_true(usage.get("used") is False, "misconfigured provider should fallback to deterministic path")
    reason = str(usage.get("fallback_reason", ""))
    assert_true("missing API key" in reason or "missing API key from env var" in reason, "expected missing key fallback")


def gate_config_precedence(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        (
            "[llm]\n"
            'provider = "openai_compatible"\n'
            "[llm.openai_compatible]\n"
            'base_url = "mock://openai/v1"\n'
            'model = "model-from-toml"\n'
            'api_key_env = "FORGE_LLM_API_KEY"\n'
            "timeout_s = 2\n"
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FORGE_LLM_MODEL"] = "model-from-env"
    env["FORGE_LLM_API_KEY"] = "test-key"

    payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--llm-model",
                "model-from-cli",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
            env=env,
        ).stdout
    )
    usage = payload.get("sections", {}).get("llm_usage", {})
    assert_true(usage.get("used") is True, "precedence test should still use provider")
    assert_true(usage.get("model") == "model-from-cli", "CLI model must override env and TOML")
    sources = usage.get("config_source", {})
    assert_true(sources.get("model") == "cli", "model source should be cli")
    assert_true(sources.get("base_url") == "toml", "base_url source should be toml")


def gate_env_file_autoload(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        (
            "[llm]\n"
            'provider = "openai_compatible"\n'
            "[llm.openai_compatible]\n"
            'base_url = "mock://openai/v1"\n'
            'model = "model-from-config"\n'
            'api_key_env = "FORGE_LLM_API_KEY"\n'
            "timeout_s = 2\n"
        ),
        encoding="utf-8",
    )
    (repo_root / ".env").write_text("FORGE_LLM_API_KEY=env-autoload-key\n", encoding="utf-8")

    env = os.environ.copy()
    env.pop("FORGE_LLM_API_KEY", None)
    payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
            env=env,
        ).stdout
    )
    usage = payload.get("sections", {}).get("llm_usage", {})
    assert_true(usage.get("provider") == "openai_compatible", ".env autoload should preserve provider from config")
    assert_true(usage.get("used") is True, ".env autoload should provide missing API key")


def gate_prompt_profile_policy(repo_root: Path) -> None:
    default_payload = parse_json_output(
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
                "describe",
            ],
            cwd=ROOT,
        ).stdout
    )
    default_usage = default_payload.get("sections", {}).get("llm_usage", {})
    assert_true(default_usage.get("prompt_profile") == "describe_onboarding", "describe should use capability-default profile")
    default_sources = default_usage.get("config_source", {})
    assert_true(
        default_sources.get("prompt_profile") == "capability_default",
        "default prompt profile source should be capability_default",
    )

    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        (
            "[llm]\n"
            'provider = "mock"\n'
            "[llm.prompt]\n"
            'profile = "review_strict"\n'
        ),
        encoding="utf-8",
    )
    mismatch_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    mismatch_usage = mismatch_payload.get("sections", {}).get("llm_usage", {})
    assert_true(mismatch_usage.get("used") is False, "invalid profile mapping should fallback")
    reason = str(mismatch_usage.get("fallback_reason", ""))
    assert_true("not allowed for capability 'query'" in reason, "expected profile-compatibility fallback reason")


def gate_run_history_and_views(repo_root: Path) -> None:
    run_cmd(["python3", str(FORGE), "--repo-root", str(repo_root), "query", "standard", "compute_price"], cwd=ROOT)
    run_cmd(["python3", str(FORGE), "--repo-root", str(repo_root), "explain", "compute_price"], cwd=ROOT)

    history_file = repo_root / ".forge" / "runs.jsonl"
    assert_true(history_file.exists(), "runs history file should exist after capability execution")

    last_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "runs", "last"],
            cwd=ROOT,
        ).stdout
    )
    last_id = int(last_payload.get("id", 0))
    assert_true(last_id > 0, "runs last should return a concrete run id")

    show_out = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "runs", str(last_id), "show", "full"],
        cwd=ROOT,
    ).stdout
    assert_true(f"Run #{last_id}" in show_out, "runs show full should print selected run id")

    rerun_out = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "runs", str(last_id), "rerun"],
        cwd=ROOT,
    ).stdout
    assert_true(len(rerun_out.strip()) > 0, "runs rerun should emit execution output")


def gate_cross_lingual_query(repo_root: Path) -> None:
    payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "query",
                "wo",
                "wird",
                "preis",
                "berechnet",
            ],
            cwd=ROOT,
        ).stdout
    )
    cross = payload.get("sections", {}).get("cross_lingual", {})
    assert_true(cross.get("source_language") == "de", "cross-lingual: expected german source language detection")
    mapped_terms = cross.get("mapped_terms", [])
    assert_true(isinstance(mapped_terms, list) and len(mapped_terms) > 0, "cross-lingual: expected mapped terms")
    likely = payload.get("sections", {}).get("likely_locations", [])
    likely_paths = [item.get("path") for item in likely if isinstance(item, dict)]
    assert_true(
        "src/service.py" in likely_paths[:5],
        "cross-lingual: expected src/service.py in top likely locations for german query",
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
    describe_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "describe"],
            cwd=ROOT,
        ).stdout
    )
    test_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "test", "src/service.py"],
            cwd=ROOT,
        ).stdout
    )

    assert_true(len(query_payload["evidence"]) > 0, "query: expected non-empty evidence")
    assert_true(len(explain_payload["evidence"]) > 0, "explain: expected non-empty evidence")
    findings = review_payload.get("sections", {}).get("findings", [])
    assert_true(len(findings) > 0, "review: expected at least one finding on controller fixture")
    first_evidence = findings[0].get("evidence", [])
    assert_true(len(first_evidence) > 0, "review: finding must include evidence")
    describe_sections = describe_payload.get("sections", {})
    assert_true("target" in describe_sections, "describe: expected target section")
    test_sections = test_payload.get("sections", {})
    assert_true("proposed_cases" in test_sections, "test: expected proposed_cases section")


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
        gate_openai_compatible_provider(temp_repo)
        gate_config_toml_fallback(temp_repo)
        gate_config_precedence(temp_repo)
        gate_env_file_autoload(temp_repo)
        gate_prompt_profile_policy(temp_repo)
        gate_run_history_and_views(temp_repo)
        gate_cross_lingual_query(temp_repo)
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
