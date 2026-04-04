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
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORGE = ROOT / "forge.py"
FIXTURE_BASIC_SRC = ROOT / "tests" / "fixtures" / "basic_repo"
FIXTURE_FRONTEND_SRC = ROOT / "tests" / "fixtures" / "frontend_repo"
FIXTURE_MIXED_SRC = ROOT / "tests" / "fixtures" / "mixed_sparse_repo"
FIXTURE_MALFORMED_SRC = ROOT / "tests" / "fixtures" / "malformed_repo"


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


def append_history_record(repo_root: Path, record: dict[str, object]) -> None:
    path = repo_root / ".forge" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True))
        fh.write("\n")


def load_runs_json(repo_root: Path) -> list[dict]:
    path = repo_root / ".forge" / "runs.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


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
        [
            "python3",
            str(FORGE),
            "--llm-provider",
            "mock",
            "--repo-root",
            str(repo_root),
            "query",
            "where",
            "is",
            "compute_price",
        ],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "explain", "compute_price"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "review", "src/controller.py"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "describe"],
        ["python3", str(FORGE), "--repo-root", str(repo_root), "test", "src/service.py"],
    ]
    for cmd in commands:
        run_cmd(cmd, cwd=ROOT)


def gate_module_invocation_compat(repo_root: Path) -> None:
    run_cmd(
        ["python3", "-m", "forge", "--repo-root", str(repo_root), "doctor"],
        cwd=ROOT,
    )
    run_cmd(
        ["python3", "-m", "forge", "--output-format", "json", "--repo-root", str(repo_root), "query", "compute_price"],
        cwd=ROOT,
    )


def gate_output_contract(repo_root: Path) -> None:
    doctor_out = run_cmd(
        ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "doctor"],
        cwd=ROOT,
    ).stdout
    query_out = run_cmd(
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
            "compute_price",
        ],
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
            expect_ok=False,
        ).stdout
    )
    planner = payload.get("sections", {}).get("query_planner", {})
    usage = planner.get("usage", {}) if isinstance(planner, dict) else {}
    assert_true(usage.get("used") is False, "misconfigured provider should fail planner usage")
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
    run_cmd(
        [
            "python3",
            str(FORGE),
            "--llm-provider",
            "mock",
            "--repo-root",
            str(repo_root),
            "query",
            "standard",
            "compute_price",
        ],
        cwd=ROOT,
    )
    run_cmd(["python3", str(FORGE), "--repo-root", str(repo_root), "explain", "compute_price"], cwd=ROOT)

    history_file = repo_root / ".forge" / "runs.jsonl"
    assert_true(history_file.exists(), "runs history file should exist after capability execution")
    before_lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    last_payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "runs", "last"],
            cwd=ROOT,
        ).stdout
    )
    last_id = int(last_payload.get("id", 0))
    assert_true(last_id > 0, "runs last should return a concrete run id")

    compact_out = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "runs", "show", str(last_id), "compact"],
        cwd=ROOT,
    ).stdout
    standard_out = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "runs", str(last_id), "standard"],
        cwd=ROOT,
    ).stdout
    show_out = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "runs", str(last_id), "show", "full"],
        cwd=ROOT,
    ).stdout

    assert_true(f"#{last_id} |" in compact_out, "runs compact should use compact one-line format")
    assert_true("Payload:" not in compact_out, "runs compact should not print payload details")
    assert_true("Payload:" in standard_out, "runs standard should include essential metadata")
    assert_true("--- Full Output ---" not in standard_out, "runs standard should not include full output block")
    assert_true(f"Run #{last_id}" in show_out, "runs show full should print selected run id")
    assert_true("--- Full Output ---" in show_out, "runs full should include full output block")

    after_show_lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(
        len(after_show_lines) == len(before_lines),
        "runs show/list/last should not mutate run history or trigger re-execution",
    )

    rerun_out = run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "runs", str(last_id), "rerun"],
        cwd=ROOT,
    ).stdout
    assert_true(len(rerun_out.strip()) > 0, "runs rerun should emit execution output")
    after_rerun_lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(
        len(after_rerun_lines) == len(after_show_lines),
        "runs rerun should execute explicitly without mutating history records",
    )


def gate_run_history_prune(repo_root: Path) -> None:
    history_file = repo_root / ".forge" / "runs.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text("", encoding="utf-8")

    for idx in range(6):
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                f"compute_price_{idx}",
            ],
            cwd=ROOT,
        )

    before_lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(len(before_lines) >= 6, "runs prune: expected seeded runs history")

    no_op = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "runs",
                "--keep-last",
                "100",
                "--older-than-days",
                "99999",
                "--dry-run",
                "prune",
            ],
            cwd=ROOT,
        ).stdout
    )
    no_op_counts = no_op.get("sections", {}).get("counts", {})
    assert_true(no_op_counts.get("removed_valid") == 0, "runs prune no-op: expected removed_valid=0")

    dry_run = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "runs",
                "--keep-last",
                "2",
                "--dry-run",
                "prune",
            ],
            cwd=ROOT,
        ).stdout
    )
    dry_counts = dry_run.get("sections", {}).get("counts", {})
    assert_true(dry_counts.get("removed_valid") >= 4, "runs prune dry-run: expected removals")
    after_dry_lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(
        len(after_dry_lines) == len(before_lines),
        "runs prune dry-run must not rewrite runs history",
    )

    apply = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "runs",
                "--keep-last",
                "2",
                "prune",
            ],
            cwd=ROOT,
        ).stdout
    )
    apply_counts = apply.get("sections", {}).get("counts", {})
    assert_true(apply_counts.get("after_valid") == 2, "runs prune apply: expected after_valid=2")
    after_apply_lines = [line for line in history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(len(after_apply_lines) == 2, "runs prune apply: expected file rewritten to kept entries")


def gate_cross_lingual_query(repo_root: Path) -> None:
    payload = parse_json_output(
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


def gate_query_planner_success(repo_root: Path) -> None:
    payload = parse_json_output(
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
                "wo",
                "wird",
                "preis",
                "berechnet",
            ],
            cwd=ROOT,
        ).stdout
    )
    planner = payload.get("sections", {}).get("query_planner", {})
    usage = planner.get("usage", {}) if isinstance(planner, dict) else {}
    assert_true(bool(planner), "query planner success: expected query_planner section")
    assert_true(usage.get("attempted") is True, "query planner success: expected attempted=true")
    assert_true(usage.get("used") is True, "query planner success: expected used=true with mock provider")
    planner_terms = planner.get("search_terms", [])
    assert_true(isinstance(planner_terms, list) and len(planner_terms) > 0, "query planner success: expected terms")
    normalized = planner.get("normalized_question_en")
    assert_true(isinstance(normalized, str) and len(normalized.strip()) > 0, "query planner success: expected normalization")


def gate_query_planner_fallback(repo_root: Path) -> None:
    payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--llm-mode",
                "off",
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "where",
                "is",
                "compute_price",
            ],
            cwd=ROOT,
            expect_ok=False,
        ).stdout
    )
    planner = payload.get("sections", {}).get("query_planner", {})
    usage = planner.get("usage", {}) if isinstance(planner, dict) else {}
    assert_true(bool(planner), "query planner fallback: expected query_planner section")
    assert_true(usage.get("used") is False, "query planner fallback: expected used=false")
    reason = str(usage.get("fallback_reason", ""))
    assert_true(
        "disabled" in reason or "provider" in reason,
        "query planner fallback: expected explicit fallback reason",
    )
    likely = payload.get("sections", {}).get("likely_locations", [])
    assert_true(isinstance(likely, list), "query planner fallback: expected likely_locations section")
    uncertainty = payload.get("uncertainty", [])
    assert_true(
        any("exact user terms only" in str(item) for item in uncertainty),
        "query planner fallback: expected explicit strict exact-term fallback note",
    )


def gate_llm_observability_redaction(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        (
            "[llm]\n"
            'provider = "mock"\n'
            "[llm.observability]\n"
            "enabled = true\n"
            'level = "debug"\n'
            "retention_count = 200\n"
            "max_file_mb = 2\n"
        ),
        encoding="utf-8",
    )
    run_cmd(
        [
            "python3",
            str(FORGE),
            "--repo-root",
            str(repo_root),
            "query",
            "standard",
            "compute_price",
        ],
        cwd=ROOT,
    )
    log_file = repo_root / ".forge" / "logs" / "llm_observability.jsonl"
    assert_true(log_file.exists(), "observability: expected .forge/logs/llm_observability.jsonl to exist")
    content = log_file.read_text(encoding="utf-8")
    assert_true("Authorization" not in content, "observability: log must not contain Authorization headers")
    assert_true("Bearer " not in content, "observability: log must not contain bearer tokens")
    assert_true('"api_key"' not in content, "observability: log must not contain raw api_key field")
    assert_true("deterministic_summary" not in content, "observability: log must not contain raw prompt payload")
    lines = [line for line in content.splitlines() if line.strip()]
    assert_true(len(lines) > 0, "observability: expected at least one log event")
    first = json.loads(lines[0])
    assert_true("capability" in first and "stage" in first, "observability: expected structured event metadata")


def gate_llm_contract_parity(repo_root: Path) -> None:
    off_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--llm-mode",
                "off",
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "query",
                "standard",
                "compute_price",
            ],
            cwd=ROOT,
            expect_ok=False,
        ).stdout
    )
    on_payload = parse_json_output(
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
    assert_true(off_payload.get("capability") == on_payload.get("capability") == "query", "parity: capability mismatch")
    assert_true(off_payload.get("profile") == on_payload.get("profile"), "parity: profile mismatch")
    for field in ("summary", "evidence", "uncertainty", "next_step", "sections"):
        assert_true(field in off_payload, f"parity/off: missing field '{field}'")
        assert_true(field in on_payload, f"parity/on: missing field '{field}'")
    off_sections = off_payload.get("sections", {})
    on_sections = on_payload.get("sections", {})
    for key in ("likely_locations", "llm_usage", "query_planner", "provenance"):
        assert_true(key in off_sections, f"parity/off: missing sections.{key}")
        assert_true(key in on_sections, f"parity/on: missing sections.{key}")


def gate_prompt_template_resolution_failure(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        (
            "[llm]\n"
            'provider = "mock"\n'
            "[llm.prompt]\n"
            'system_template = "prompts/system/does_not_exist.txt"\n'
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
                "explain",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    usage = payload.get("sections", {}).get("llm_usage", {})
    assert_true(usage.get("used") is False, "prompt template failure: expected deterministic fallback")
    reason = str(usage.get("fallback_reason", ""))
    assert_true("missing system template" in reason, "prompt template failure: expected missing-template reason")


def gate_doctor_config_validate_matrix_malformed(repo_root: Path) -> None:
    doctor = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "doctor"],
            cwd=ROOT,
        ).stdout
    )
    cfg_validate = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "config", "validate"],
            cwd=ROOT,
        ).stdout
    )
    doctor_sections = doctor.get("sections", {})
    cfg_sections = cfg_validate.get("sections", {})
    assert_true(doctor_sections.get("status") == "fail", "doctor matrix: malformed fixture should fail")
    assert_true(cfg_sections.get("status") == "fail", "config validate matrix: malformed fixture should fail")
    doctor_checks = doctor_sections.get("checks", [])
    cfg_checks = cfg_sections.get("checks", [])
    assert_true(isinstance(doctor_checks, list) and doctor_checks, "doctor matrix: expected checks")
    assert_true(isinstance(cfg_checks, list) and cfg_checks, "config validate matrix: expected checks")
    doctor_validation = [item for item in doctor_checks if isinstance(item, dict) and item.get("key") == "config_validation"]
    cfg_validation = [item for item in cfg_checks if isinstance(item, dict) and item.get("key") == "config_validation"]
    assert_true(doctor_validation and doctor_validation[0].get("status") == "fail", "doctor matrix: config_validation should fail")
    assert_true(cfg_validation and cfg_validation[0].get("status") == "fail", "config validate matrix: config_validation should fail")


def gate_frontend_fixture(frontend_repo: Path) -> None:
    describe_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(frontend_repo),
                "describe",
            ],
            cwd=ROOT,
        ).stdout
    )
    languages = describe_payload.get("sections", {}).get("technologies", {}).get("languages", [])
    assert_true(isinstance(languages, list), "frontend fixture: expected describe technologies.languages list")
    assert_true(
        any(str(item) in {"React TSX", "TypeScript", "JavaScript"} for item in languages),
        "frontend fixture: expected frontend language detection",
    )

def gate_mixed_fixture_describe(mixed_repo: Path) -> None:
    payload = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(mixed_repo), "describe"],
            cwd=ROOT,
        ).stdout
    )
    languages = payload.get("sections", {}).get("technologies", {}).get("languages", [])
    assert_true(isinstance(languages, list), "mixed fixture: expected technologies.languages list")
    lang_set = {str(item) for item in languages}
    assert_true("Python" in lang_set, "mixed fixture: expected Python detection")
    assert_true("JavaScript" in lang_set, "mixed fixture: expected JavaScript detection")


def gate_external_review_rules(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "review-rules.toml").write_text(
        (
            "[[rule]]\n"
            'id = "controller_sql_custom"\n'
            'title = "Custom SQL Keyword in Controller"\n'
            'severity = "high"\n'
            'pattern = "SELECT|INSERT|UPDATE|DELETE"\n'
            'path_includes = ["controller"]\n'
            'explanation = "Controller includes SQL keyword via external rule."\n'
            'recommendation = "Move SQL to repository/service."\n'
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
                "review",
                "src/controller.py",
            ],
            cwd=ROOT,
        ).stdout
    )
    sections = payload.get("sections", {})
    findings = sections.get("findings", [])
    custom = [item for item in findings if isinstance(item, dict) and item.get("rule_id") == "controller_sql_custom"]
    assert_true(custom, "external rules: expected custom rule finding with rule_id")
    review_rules = sections.get("review_rules", {})
    assert_true(review_rules.get("loaded") == 1, "external rules: expected loaded=1")
    assert_true(review_rules.get("errors") == [], "external rules: expected no rule errors")


def gate_external_review_rules_invalid(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "review-rules.toml").write_text(
        (
            "[[rule]]\n"
            'id = "bad_regex"\n'
            'title = "Invalid regex rule"\n'
            'severity = "high"\n'
            'pattern = "(unclosed"\n'
            'explanation = "broken rule for gate"\n'
        ),
        encoding="utf-8",
    )
    doctor = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "doctor"],
            cwd=ROOT,
        ).stdout
    )
    checks = doctor.get("sections", {}).get("checks", [])
    review_rule_checks = [item for item in checks if isinstance(item, dict) and item.get("key") == "review_rules"]
    assert_true(review_rule_checks, "external rules invalid: expected review_rules doctor check")
    status = review_rule_checks[0].get("status")
    assert_true(status in {"warn", "fail"}, "external rules invalid: expected warn/fail status")

    review_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "review",
                "src/controller.py",
            ],
            cwd=ROOT,
        ).stdout
    )
    review_rules = review_payload.get("sections", {}).get("review_rules", {})
    errors = review_rules.get("errors", [])
    assert_true(isinstance(errors, list) and len(errors) >= 1, "external rules invalid: expected surfaced rule error list")


def gate_from_run_references(repo_root: Path) -> None:
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
            "compute_price",
        ],
        cwd=ROOT,
    )
    query_run = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "runs", "last"],
            cwd=ROOT,
        ).stdout
    )
    query_run_id = int(query_run.get("id", 0))
    assert_true(query_run_id > 0, "from-run: expected query run id")

    explain_from_query = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "explain",
                "--from-run",
                str(query_run_id),
            ],
            cwd=ROOT,
        ).stdout
    )
    explain_sections = explain_from_query.get("sections", {})
    assert_true(explain_sections.get("source_run_id") == query_run_id, "from-run: explain should expose source_run_id")
    assert_true(
        explain_sections.get("source_run_capability") == "query",
        "from-run: explain should expose source_run_capability=query",
    )
    assert_true(
        isinstance(explain_sections.get("resolved_from_run_payload"), str),
        "from-run: explain should expose resolved_from_run_payload",
    )

    run_cmd(
        [
            "python3",
            str(FORGE),
            "--output-format",
            "json",
            "--repo-root",
            str(repo_root),
            "review",
            "src/controller.py",
        ],
        cwd=ROOT,
    )
    review_run = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "runs", "last"],
            cwd=ROOT,
        ).stdout
    )
    review_run_id = int(review_run.get("id", 0))
    assert_true(review_run_id > 0, "from-run: expected review run id")

    test_from_review = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "test",
                "--from-run",
                str(review_run_id),
            ],
            cwd=ROOT,
        ).stdout
    )
    test_sections = test_from_review.get("sections", {})
    assert_true(test_sections.get("source_run_id") == review_run_id, "from-run: test should expose source_run_id")
    assert_true(
        test_sections.get("source_run_capability") == "review",
        "from-run: test should expose source_run_capability=review",
    )

    invalid = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "explain",
                "--from-run",
                "999999",
            ],
            cwd=ROOT,
            expect_ok=False,
        ).stdout
    )
    invalid_sections = invalid.get("sections", {})
    assert_true(
        invalid_sections.get("status") == "from_run_resolution_failed",
        "from-run: invalid id should return explicit resolution failure status",
    )


def gate_run_history_contract_always_persisted(repo_root: Path) -> None:
    run_cmd(
        [
            "python3",
            str(FORGE),
            "--llm-provider",
            "mock",
            "--repo-root",
            str(repo_root),
            "query",
            "compute_price",
        ],
        cwd=ROOT,
    )
    records = load_runs_json(repo_root)
    assert_true(records, "history contract: expected at least one run record")
    last = records[-1]
    output = last.get("output", {})
    contract = output.get("contract") if isinstance(output, dict) else None
    assert_true(isinstance(contract, dict), "history contract: expected output.contract for text-mode query run")
    assert_true(contract.get("capability") == "query", "history contract: expected query capability in contract")
    sections = contract.get("sections", {})
    assert_true(isinstance(sections, dict), "history contract: expected sections object in stored contract")
    likely = sections.get("likely_locations", [])
    assert_true(isinstance(likely, list), "history contract: expected likely_locations list")
    execution = last.get("execution", {})
    protocol_events = execution.get("protocol_events") if isinstance(execution, dict) else None
    assert_true(isinstance(protocol_events, list), "history contract: expected execution.protocol_events list")
    assert_true(len(protocol_events) >= 4, "history contract: expected baseline protocol events")
    first_event = protocol_events[0] if protocol_events else {}
    for key in ("event_id", "run_id", "timestamp", "capability", "step_name", "step_type", "status", "metadata"):
        assert_true(key in first_event, f"history contract: protocol event missing key '{key}'")

    run_id = int(last.get("id", 0))
    assert_true(run_id > 0, "history contract: expected valid run id")
    explain_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "explain",
                "--from-run",
                str(run_id),
            ],
            cwd=ROOT,
        ).stdout
    )
    explain_sections = explain_payload.get("sections", {})
    assert_true(
        explain_sections.get("source_run_id") == run_id,
        "history contract: expected explain --from-run to resolve from text-mode run",
    )
    assert_true(
        explain_sections.get("source_run_capability") == "query",
        "history contract: expected source_run_capability=query",
    )


def gate_protocol_log_storage_jsonl(repo_root: Path) -> None:
    config_path = repo_root / ".forge" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "[logs.protocol]\n"
        "max_file_size_bytes = 1200\n"
        "max_event_age_days = 3650\n"
        "max_events_count = 100\n",
        encoding="utf-8",
    )

    for idx in range(5):
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "query",
                f"compute_price_{idx}",
            ],
            cwd=ROOT,
        )

    logs_dir = repo_root / ".forge" / "logs"
    events_file = logs_dir / "events.jsonl"
    assert_true(events_file.exists(), "protocol log: expected .forge/logs/events.jsonl to exist")
    lines = [line for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(bool(lines), "protocol log: expected non-empty events.jsonl")
    for raw in lines:
        item = parse_json_output(raw)
        for key in ("event_id", "run_id", "timestamp", "capability", "step_name", "step_type", "status", "metadata"):
            assert_true(key in item, f"protocol log: expected key '{key}' in event line")

    archives = sorted(logs_dir.glob("events-*.jsonl"))
    assert_true(bool(archives), "protocol log: expected timestamped rotation archive file")

    config_path.write_text(
        "[logs.protocol]\n"
        "max_file_size_bytes = 500000\n"
        "max_event_age_days = 3650\n"
        "max_events_count = 100\n",
        encoding="utf-8",
    )
    for idx in range(8):
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--llm-provider",
                "mock",
                "--repo-root",
                str(repo_root),
                "query",
                f"compute_price_limit_{idx}",
            ],
            cwd=ROOT,
        )
    lines_after_limit = [line for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert_true(
        len(lines_after_limit) <= 100,
        "protocol log: expected max_events_count retention to cap active events.jsonl",
    )


def gate_evidence_quality(repo_root: Path) -> None:
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
                "compute_price",
            ],
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


def gate_explain_structured_synthesis(repo_root: Path) -> None:
    explain_standard = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "explain",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    sections = explain_standard.get("sections", {})
    evidence_facts = sections.get("evidence_facts", [])
    inference_points = sections.get("inference_points", [])
    confidence = sections.get("confidence", [])

    assert_true(isinstance(evidence_facts, list) and len(evidence_facts) > 0, "explain synthesis: expected evidence_facts")
    assert_true(isinstance(inference_points, list) and len(inference_points) > 0, "explain synthesis: expected inference_points")
    assert_true(isinstance(confidence, list) and len(confidence) == len(inference_points), "explain synthesis: confidence cardinality mismatch")

    fact_ids = {item.get("id") for item in evidence_facts if isinstance(item, dict)}
    for point in inference_points:
        assert_true(isinstance(point, dict), "explain synthesis: inference point must be object")
        refs = point.get("evidence_ids", [])
        assert_true(isinstance(refs, list) and len(refs) > 0, "explain synthesis: inference must reference evidence ids")
        assert_true(
            any(ref in fact_ids for ref in refs),
            "explain synthesis: inference evidence refs must map to evidence_facts ids",
        )

    explain_detailed = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "explain",
                "detailed",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    detailed_sections = explain_detailed.get("sections", {})
    alternatives = detailed_sections.get("role_hypothesis_alternatives", [])
    assert_true(
        isinstance(alternatives, list),
        "explain synthesis: detailed profile should include role_hypothesis_alternatives list",
    )


def gate_mode_capability_contract_query_read_only(repo_root: Path) -> None:
    before = snapshot_repo_files(repo_root)
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
                "please",
                "fix",
                "and",
                "rewrite",
                "src/service.py",
            ],
            cwd=ROOT,
        ).stdout
    )
    sections = payload.get("sections", {})
    violations = sections.get("policy_violations", [])
    assert_true(isinstance(violations, list) and violations, "mode contract: expected policy_violations for write-like query")
    first = violations[0] if violations else {}
    assert_true(first.get("capability") == "query", "mode contract: expected capability=query violation")
    assert_true(first.get("blocked_action") == "repo_write", "mode contract: expected blocked_action=repo_write")
    uncertainty = payload.get("uncertainty", [])
    assert_true(
        any("read-only" in str(item).lower() and "blocked" in str(item).lower() for item in uncertainty),
        "mode contract: expected explicit read-only boundary note in uncertainty",
    )
    after = snapshot_repo_files(repo_root)
    assert_true(before == after, "mode contract: adversarial query must not modify repository files")


def gate_query_action_orchestration(repo_root: Path) -> None:
    payload = parse_json_output(
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
    orchestration = payload.get("sections", {}).get("action_orchestration", {})
    assert_true(isinstance(orchestration, dict) and orchestration, "orchestration: expected action_orchestration section")
    done_reason = orchestration.get("done_reason")
    assert_true(
        done_reason in {"sufficient_evidence", "budget_exhausted", "policy_blocked"},
        "orchestration: invalid done_reason",
    )
    usage = orchestration.get("usage", {})
    assert_true(isinstance(usage, dict), "orchestration: usage must be object")
    decisions = orchestration.get("decisions", [])
    assert_true(isinstance(decisions, list), "orchestration: decisions must be list")
    if decisions:
        first = decisions[0]
        assert_true(isinstance(first, dict), "orchestration: first decision must be object")
        assert_true(first.get("decision") in {"continue", "stop"}, "orchestration: invalid decision value")
        assert_true(isinstance(first.get("reason"), str), "orchestration: reason must be string")
        assert_true(first.get("confidence") in {"low", "medium", "high"}, "orchestration: invalid confidence value")


def gate_adaptive_query_explain_feedback(repo_root: Path) -> None:
    payload = parse_json_output(
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
                "In",
                "welchen",
                "Dateien",
                "wird",
                "ein",
                "LLM",
                "eingesetzt?",
            ],
            cwd=ROOT,
        ).stdout
    )
    sections = payload.get("sections", {})
    feedback = sections.get("explain_feedback", [])
    assert_true(isinstance(feedback, list) and feedback, "adaptive query: expected explain_feedback section")
    first = feedback[0]
    assert_true(isinstance(first, dict), "adaptive query: feedback entry must be object")
    assert_true(
        first.get("linkage_confidence") in {"low", "medium", "high"},
        "adaptive query: invalid linkage_confidence value",
    )
    assert_true(isinstance(first.get("rationale"), list), "adaptive query: expected rationale list")
    likely = sections.get("likely_locations", [])
    assert_true(isinstance(likely, list) and likely, "adaptive query: expected likely_locations")
    assert_true("action_orchestration" in sections, "adaptive query: expected action_orchestration section")
    orchestration = sections.get("action_orchestration", {})
    assert_true(isinstance(orchestration, dict), "adaptive query: action_orchestration should be object")
    assert_true(
        orchestration.get("done_reason") in {"sufficient_evidence", "budget_exhausted", "policy_blocked"},
        "adaptive query: invalid done_reason",
    )
    assert_true(
        all(
            isinstance(item, dict) and item.get("linkage_confidence") in {"low", "medium", "high"}
            for item in feedback[:5]
        ),
        "adaptive query: expected valid linkage_confidence values",
    )


def gate_index_explain_summary_enrichment(repo_root: Path) -> None:
    run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "index"],
        cwd=ROOT,
    )
    index_path = repo_root / ".forge" / "index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    enrichment = payload.get("enrichment", {})
    assert_true(isinstance(enrichment, dict), "index enrichment: expected enrichment object")
    assert_true(enrichment.get("enabled") is True, "index enrichment: expected enabled=true by default")
    files = payload.get("entries", {}).get("files", [])
    assert_true(isinstance(files, list) and files, "index enrichment: expected file entries")

    first = files[0]
    assert_true(isinstance(first, dict), "index enrichment: first file entry should be object")
    assert_true("content_hash" in first, "index enrichment: expected content_hash field")
    assert_true("explain_summary" in first, "index enrichment: expected explain_summary field")
    assert_true("summary_version" in first, "index enrichment: expected summary_version field")
    assert_true("summary_updated_at" in first, "index enrichment: expected summary_updated_at field")

    first_path = first.get("path")
    assert_true(isinstance(first_path, str), "index enrichment: first file path should be string")
    first_updated_at = first.get("summary_updated_at")

    run_cmd(
        ["python3", str(FORGE), "--repo-root", str(repo_root), "index"],
        cwd=ROOT,
    )
    payload_again = json.loads(index_path.read_text(encoding="utf-8"))
    files_again = payload_again.get("entries", {}).get("files", [])
    first_again = next((item for item in files_again if isinstance(item, dict) and item.get("path") == first_path), None)
    assert_true(isinstance(first_again, dict), "index enrichment: expected same file on rebuild")
    assert_true(
        first_again.get("summary_updated_at") == first_updated_at,
        "index enrichment: summary timestamp should be reused when hash/version unchanged",
    )

    target_file = repo_root / str(first_path)
    original = target_file.read_text(encoding="utf-8")
    target_file.write_text(original + "\n# feature039-touch\n", encoding="utf-8")
    try:
        run_cmd(
            ["python3", str(FORGE), "--repo-root", str(repo_root), "index"],
            cwd=ROOT,
        )
    finally:
        target_file.write_text(original, encoding="utf-8")

    payload_changed = json.loads(index_path.read_text(encoding="utf-8"))
    files_changed = payload_changed.get("entries", {}).get("files", [])
    first_changed = next((item for item in files_changed if isinstance(item, dict) and item.get("path") == first_path), None)
    assert_true(isinstance(first_changed, dict), "index enrichment: changed file should still be indexed")
    assert_true(
        first_changed.get("summary_updated_at") != first_updated_at,
        "index enrichment: changed file should trigger summary recomputation",
    )

    query_payload = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "query",
                "compute_price",
            ],
            cwd=ROOT,
        ).stdout
    )
    index_summaries = query_payload.get("sections", {}).get("index_explain_summaries", [])
    assert_true(isinstance(index_summaries, list), "index enrichment: query should expose index_explain_summaries list")


def gate_explicit_mode_transition_workflows(repo_root: Path) -> None:
    forge_dir = repo_root / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "config.toml").write_text(
        "\n".join(
            [
                "[transitions]",
                "require_confirmation = true",
                "",
                "[transitions.gates]",
                'review_to_test_min_severity = "medium"',
                "test_to_fix_require_failure = true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    existing = load_runs_json(repo_root)
    next_id = (max((int(item.get("id", 0)) for item in existing), default=0) + 1) if existing else 1

    fix_record = {
        "id": next_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": {"capability": "fix", "profile": "standard", "payload": "src/controller.py", "argv": []},
        "execution": {"exit_code": 0, "output_format": "json"},
        "output": {
            "text": "",
            "contract": {
                "capability": "fix",
                "profile": "standard",
                "summary": "Seeded fix run for transition gate tests.",
                "evidence": [],
                "uncertainty": [],
                "next_step": "Run: forge review --from-run <id>",
                "sections": {"resolved_target": {"path": "src/controller.py", "source": "path"}},
            },
        },
    }
    append_history_record(repo_root, fix_record)

    blocked_missing_confirm = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "review",
                "--from-run",
                str(next_id),
            ],
            cwd=ROOT,
            expect_ok=False,
        ).stdout
    )
    assert_true(
        blocked_missing_confirm.get("sections", {}).get("status") == "from_run_resolution_failed",
        "mode transitions: expected failure without explicit confirmation",
    )
    assert_true(
        any("confirmation" in str(item).lower() for item in blocked_missing_confirm.get("uncertainty", [])),
        "mode transitions: expected explicit confirmation hint",
    )

    review_from_fix = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "review",
                "--from-run",
                str(next_id),
                "--confirm-transition",
            ],
            cwd=ROOT,
        ).stdout
    )
    review_sections = review_from_fix.get("sections", {})
    assert_true(review_sections.get("transition_source_mode") == "fix", "mode transitions: expected source_mode=fix")
    assert_true(review_sections.get("transition_target_mode") == "review", "mode transitions: expected target_mode=review")
    assert_true(review_sections.get("transition_policy_reason") == "transition_allowed", "mode transitions: expected transition_allowed")
    decisions = review_sections.get("transition_gate_decisions", [])
    assert_true(isinstance(decisions, list) and decisions, "mode transitions: expected transition_gate_decisions")

    review_run = parse_json_output(
        run_cmd(
            ["python3", str(FORGE), "--output-format", "json", "--repo-root", str(repo_root), "runs", "last"],
            cwd=ROOT,
        ).stdout
    )
    review_run_id = int(review_run.get("id", 0))
    assert_true(review_run_id > 0, "mode transitions: expected review run id after fix->review")

    test_from_review = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "test",
                "--from-run",
                str(review_run_id),
                "--confirm-transition",
            ],
            cwd=ROOT,
        ).stdout
    )
    test_sections = test_from_review.get("sections", {})
    assert_true(test_sections.get("transition_source_mode") == "review", "mode transitions: expected source_mode=review")
    assert_true(test_sections.get("transition_target_mode") == "test", "mode transitions: expected target_mode=test")
    test_decisions = test_sections.get("transition_gate_decisions", [])
    assert_true(isinstance(test_decisions, list) and test_decisions, "mode transitions: expected test transition decisions")
    threshold_gates = [item for item in test_decisions if isinstance(item, dict) and item.get("gate") == "review_findings_threshold"]
    assert_true(threshold_gates, "mode transitions: expected review_findings_threshold gate")
    assert_true(
        threshold_gates[0].get("status") == "pass",
        "mode transitions: expected review_findings_threshold gate to pass",
    )

    blocked_disallowed = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "describe",
                "--from-run",
                str(next_id),
                "--confirm-transition",
            ],
            cwd=ROOT,
            expect_ok=False,
        ).stdout
    )
    assert_true(
        blocked_disallowed.get("sections", {}).get("status") == "from_run_resolution_failed",
        "mode transitions: expected disallowed transition to fail",
    )
    assert_true(
        any("blocked by policy" in str(item).lower() for item in blocked_disallowed.get("uncertainty", [])),
        "mode transitions: expected policy block reason",
    )

    low_review_record = {
        "id": next_id + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": {"capability": "review", "profile": "standard", "payload": "src/controller.py", "argv": []},
        "execution": {"exit_code": 0, "output_format": "json"},
        "output": {
            "text": "",
            "contract": {
                "capability": "review",
                "profile": "standard",
                "summary": "Seeded low-severity review run for transition gate tests.",
                "evidence": [],
                "uncertainty": [],
                "next_step": "Run: forge test --from-run <id>",
                "sections": {
                    "findings": [
                        {
                            "title": "low-severity-only",
                            "severity": "low",
                            "explanation": "seeded",
                            "recommendation": "seeded",
                            "rule_id": "seed.low",
                            "evidence": [{"path": "src/controller.py", "line": 1, "text": "seed"}],
                        }
                    ]
                },
            },
        },
    }
    append_history_record(repo_root, low_review_record)

    blocked_threshold = parse_json_output(
        run_cmd(
            [
                "python3",
                str(FORGE),
                "--output-format",
                "json",
                "--repo-root",
                str(repo_root),
                "test",
                "--from-run",
                str(next_id + 1),
                "--confirm-transition",
            ],
            cwd=ROOT,
            expect_ok=False,
        ).stdout
    )
    assert_true(
        blocked_threshold.get("sections", {}).get("status") == "from_run_resolution_failed",
        "mode transitions: expected threshold gate failure for low-only review",
    )
    assert_true(
        any("threshold" in str(item).lower() for item in blocked_threshold.get("uncertainty", [])),
        "mode transitions: expected threshold failure reason",
    )


def gate_effect_boundaries(repo_root: Path) -> None:
    before = snapshot_repo_files(repo_root)
    read_only_commands = [
        ["python3", str(FORGE), "--llm-provider", "mock", "--repo-root", str(repo_root), "query", "compute_price"],
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
        ["python3", str(FORGE), "--llm-provider", "mock", "--repo-root", str(repo_root), "query", "compute_price"],
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
        if parts and parts[0] == "query":
            cmd = ["python3", str(FORGE), "--llm-provider", "mock", "--repo-root", str(repo_root), *parts]
        out = run_cmd(cmd, cwd=ROOT).stdout
        assert_true("Index: not available" in out or "Index: skipped" in out, f"{parts[0]}: expected index fallback message")


def run_all_gates() -> None:
    with tempfile.TemporaryDirectory(prefix="forge-gates-") as temp_dir:
        temp_repo = Path(temp_dir) / "repo-basic"
        temp_repo_frontend = Path(temp_dir) / "repo-frontend"
        temp_repo_mixed = Path(temp_dir) / "repo-mixed"
        temp_repo_malformed = Path(temp_dir) / "repo-malformed"
        temp_repo_promptfail = Path(temp_dir) / "repo-promptfail"
        temp_repo_rules = Path(temp_dir) / "repo-rules"
        temp_repo_rules_invalid = Path(temp_dir) / "repo-rules-invalid"
        shutil.copytree(FIXTURE_BASIC_SRC, temp_repo)
        shutil.copytree(FIXTURE_FRONTEND_SRC, temp_repo_frontend)
        shutil.copytree(FIXTURE_MIXED_SRC, temp_repo_mixed)
        shutil.copytree(FIXTURE_MALFORMED_SRC, temp_repo_malformed)
        shutil.copytree(FIXTURE_BASIC_SRC, temp_repo_promptfail)
        shutil.copytree(FIXTURE_BASIC_SRC, temp_repo_rules)
        shutil.copytree(FIXTURE_BASIC_SRC, temp_repo_rules_invalid)

        gate_behavior_smoke(temp_repo)
        gate_module_invocation_compat(temp_repo)
        gate_output_contract(temp_repo)
        gate_llm_path(temp_repo)
        gate_llm_contract_parity(temp_repo)
        gate_openai_compatible_provider(temp_repo)
        gate_config_toml_fallback(temp_repo)
        gate_config_precedence(temp_repo)
        gate_env_file_autoload(temp_repo)
        gate_prompt_profile_policy(temp_repo)
        gate_prompt_template_resolution_failure(temp_repo_promptfail)
        gate_run_history_and_views(temp_repo)
        gate_run_history_prune(temp_repo)
        gate_cross_lingual_query(temp_repo)
        gate_query_planner_success(temp_repo)
        gate_query_planner_fallback(temp_repo)
        gate_llm_observability_redaction(temp_repo)
        gate_evidence_quality(temp_repo)
        gate_explain_structured_synthesis(temp_repo)
        gate_mode_capability_contract_query_read_only(temp_repo)
        gate_query_action_orchestration(temp_repo)
        gate_adaptive_query_explain_feedback(temp_repo)
        gate_index_explain_summary_enrichment(temp_repo)
        gate_explicit_mode_transition_workflows(temp_repo)
        gate_effect_boundaries(temp_repo)
        gate_fallback_with_and_without_index(temp_repo)
        gate_frontend_fixture(temp_repo_frontend)
        gate_mixed_fixture_describe(temp_repo_mixed)
        gate_doctor_config_validate_matrix_malformed(temp_repo_malformed)
        gate_external_review_rules(temp_repo_rules)
        gate_external_review_rules_invalid(temp_repo_rules_invalid)
        gate_from_run_references(temp_repo)
        gate_run_history_contract_always_persisted(temp_repo)
        gate_protocol_log_storage_jsonl(temp_repo)


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
