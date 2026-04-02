from __future__ import annotations

from core.capability_model import CommandRequest
from core.effects import ExecutionSession


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    print("=== FORGE DESCRIBE ===")
    print(f"Profile: {request.profile.value}")
    if request.payload:
        print(f"Target: {request.payload}")

    # TODO:
    # - scan repo structure
    # - identify main components
    # - summarize

    print("Not implemented yet.")
    return 0
