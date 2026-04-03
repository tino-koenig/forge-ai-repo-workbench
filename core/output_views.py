"""Human-first text output view helpers."""

from __future__ import annotations


def resolve_view(args) -> str:
    if getattr(args, "details", False):
        return "full"
    return getattr(args, "view", "standard")


def is_compact(view: str) -> bool:
    return view == "compact"


def is_full(view: str) -> bool:
    return view == "full"

