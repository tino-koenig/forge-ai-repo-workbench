"""Externalized review rule loading and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import tomli


@dataclass(frozen=True)
class ReviewRule:
    rule_id: str
    title: str
    severity: str
    pattern: str
    regex: re.Pattern[str]
    explanation: str
    recommendation: str | None
    path_includes: list[str]
    path_excludes: list[str]


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate:
            out.append(candidate)
    return out


def load_review_rules(repo_root: Path) -> tuple[list[ReviewRule], list[str]]:
    path = repo_root / ".forge" / "review-rules.toml"
    if not path.exists():
        return [], []
    try:
        payload = tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError) as exc:
        return [], [f"invalid review rules TOML: {exc}"]

    entries = payload.get("rule")
    if entries is None:
        return [], []
    if not isinstance(entries, list):
        return [], ["review-rules: expected [[rule]] array"]

    valid: list[ReviewRule] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(entries, start=1):
        prefix = f"rule[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected table")
            continue
        rule_id = item.get("id")
        title = item.get("title")
        severity = item.get("severity")
        pattern = item.get("pattern")
        explanation = item.get("explanation")
        recommendation = item.get("recommendation")
        path_includes = _as_string_list(item.get("path_includes"))
        path_excludes = _as_string_list(item.get("path_excludes"))

        if not isinstance(rule_id, str) or not rule_id.strip():
            errors.append(f"{prefix}: missing non-empty id")
            continue
        rule_id = rule_id.strip()
        if rule_id in seen_ids:
            errors.append(f"{prefix}: duplicate id '{rule_id}'")
            continue
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{prefix}: missing non-empty title")
            continue
        if severity not in {"low", "medium", "high"}:
            errors.append(f"{prefix}: severity must be low|medium|high")
            continue
        if not isinstance(pattern, str) or not pattern.strip():
            errors.append(f"{prefix}: missing non-empty pattern")
            continue
        if not isinstance(explanation, str) or not explanation.strip():
            errors.append(f"{prefix}: missing non-empty explanation")
            continue
        if recommendation is not None and not isinstance(recommendation, str):
            errors.append(f"{prefix}: recommendation must be a string when set")
            continue
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            errors.append(f"{prefix}: invalid regex pattern: {exc}")
            continue
        seen_ids.add(rule_id)
        valid.append(
            ReviewRule(
                rule_id=rule_id,
                title=title.strip(),
                severity=severity,
                pattern=pattern,
                regex=regex,
                explanation=explanation.strip(),
                recommendation=recommendation.strip() if isinstance(recommendation, str) and recommendation.strip() else None,
                path_includes=path_includes,
                path_excludes=path_excludes,
            )
        )
    return valid, errors

