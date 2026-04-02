"""Runtime execution for capability requests."""

from __future__ import annotations

from argparse import Namespace

from core.capability_model import Capability, CommandRequest
from core.effects import ExecutionSession
from modes.describe import run as run_describe
from modes.explain import run as run_explain
from modes.query import run as run_query
from modes.review import run as run_review
from modes.test import run as run_test


HANDLERS = {
    Capability.QUERY: run_query,
    Capability.EXPLAIN: run_explain,
    Capability.REVIEW: run_review,
    Capability.DESCRIBE: run_describe,
    Capability.TEST: run_test,
}


def execute(request: CommandRequest, args: Namespace) -> int:
    session = ExecutionSession(request=request)
    handler = HANDLERS[request.capability]
    return handler(request=request, args=args, session=session)
