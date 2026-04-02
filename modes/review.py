from __future__ import annotations

from core.capability_model import CommandRequest
from core.effects import ExecutionSession


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    print("=== FORGE REVIEW ===")
    print(f"Profile: {request.profile.value}")
    print(f"Target: {request.payload}")

    # TODO:
    # - load file(s)
    # - run heuristics
    # - output findings

    print("Not implemented yet.")
    return 0
