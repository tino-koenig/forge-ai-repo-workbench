from __future__ import annotations

from core.capability_model import CommandRequest
from core.effects import ExecutionSession


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    print("=== FORGE EXPLAIN ===")
    print(f"Profile: {request.profile.value}")
    print(f"Target: {request.payload}")

    # TODO:
    # - inspect target
    # - explain role and behavior
    # - include evidence and uncertainty

    print("Not implemented yet.")
    return 0
