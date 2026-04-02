"""Repo access helpers that enforce Forge effect boundaries."""

from __future__ import annotations

from pathlib import Path

from core.capability_model import EffectClass
from core.effects import ExecutionSession


IGNORED_DIRS = {
    ".git",
    ".forge",
    "__pycache__",
    ".idea",
    ".venv",
    "node_modules",
}

TEXT_FILE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
}


def iter_repo_files(root: Path, session: ExecutionSession) -> list[Path]:
    session.record_effect(EffectClass.READ_ONLY, "list repository files")
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        result.append(path)
    return result


def read_text_file(path: Path, session: ExecutionSession) -> str | None:
    session.record_effect(EffectClass.READ_ONLY, f"read file {path}")
    if path.suffix.lower() not in TEXT_FILE_EXTENSIONS:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
