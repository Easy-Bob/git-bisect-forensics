"""pin_truth, the bisect task's reference: every commit's tests run, out of the agent's sight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contract import BisectInput, PinOutput, Status
from plugin.history import history_sha256, load_history
from plugin.testrun import test_commit


def table_sha256(ids: list[str], statuses: list[Status]) -> str:
    """The same digest verifier/checks.py computes, so the verifier can tell an altered table."""
    rows = [[commit, status.value] for commit, status in zip(ids, statuses, strict=True)]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def pin_truth(value: BisectInput, workspace: Path) -> PinOutput:
    history = load_history(value.repo)
    folder = workspace / "pin" / "tree"
    ids, statuses = [], []
    for position, commit in enumerate(history["commits"], start=1):
        status, _ = test_commit(history, position, folder)
        ids.append(commit["id"])
        statuses.append(status)
    return PinOutput(
        repo=value.repo,
        ids=ids,
        statuses=statuses,
        history_sha256=history_sha256(value.repo),
        table_sha256=table_sha256(ids, statuses),
    )
