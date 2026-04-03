"""Runtime execution for capability requests."""

from __future__ import annotations

from argparse import Namespace

from core.capability_model import Capability, CommandRequest
from core.effects import ExecutionSession
from modes.describe import run as run_describe
from modes.doctor import run as run_doctor
from modes.explain import run as run_explain
from modes.index import run as run_index
from modes.init import run as run_init
from modes.query import run as run_query
from modes.review import run as run_review
from modes.runs import run as run_runs
from modes.test import run as run_test


HANDLERS = {
    Capability.INIT: run_init,
    Capability.INDEX: run_index,
    Capability.QUERY: run_query,
    Capability.EXPLAIN: run_explain,
    Capability.REVIEW: run_review,
    Capability.DESCRIBE: run_describe,
    Capability.TEST: run_test,
    Capability.DOCTOR: run_doctor,
    Capability.RUNS: run_runs,
}


def execute(request: CommandRequest, args: Namespace) -> int:
    session = ExecutionSession(request=request)
    handler = HANDLERS[request.capability]
    return handler(request=request, args=args, session=session)
