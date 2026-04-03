"""Canonical output contract helpers for Forge capabilities."""

from __future__ import annotations

from contextvars import ContextVar
import json
from typing import Any

_LAST_CONTRACT: ContextVar[dict[str, Any] | None] = ContextVar("forge_last_contract", default=None)


def build_contract(
    *,
    capability: str,
    profile: str,
    summary: str,
    evidence: list[dict[str, Any]],
    uncertainty: list[str],
    next_step: str,
    sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "capability": capability,
        "profile": profile,
        "summary": summary,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "next_step": next_step,
    }
    if sections:
        payload["sections"] = sections
    _LAST_CONTRACT.set(payload)
    return payload


def emit_contract_json(contract: dict[str, Any]) -> None:
    _LAST_CONTRACT.set(contract)
    print(json.dumps(contract, indent=2, sort_keys=True))


def reset_last_contract() -> None:
    _LAST_CONTRACT.set(None)


def consume_last_contract() -> dict[str, Any] | None:
    payload = _LAST_CONTRACT.get()
    _LAST_CONTRACT.set(None)
    return payload
