"""run_tests: a repo's tests at up to 7 commits of the latest run, each call receipted."""

from __future__ import annotations

from pathlib import Path

from contract import CommitResult, RunInput, RunOutput
from plugin.history import check_position, history_sha256, load_history
from plugin.runs import MAX_CALLS, append_receipt, bisect_folder, latest_run, receipts
from plugin.testrun import test_commit

MAX_POSITIONS = 7


def run_tests(value: RunInput, workspace: Path) -> RunOutput:
    positions = value.positions
    if not 1 <= len(positions) <= MAX_POSITIONS:
        raise ValueError(f"run_tests takes 1 to {MAX_POSITIONS} positions, not {len(positions)}")
    if len(set(positions)) != len(positions):
        raise ValueError("a position is asked twice")
    history = load_history(value.repo)
    for position in positions:
        check_position(history, position)
    run = latest_run(workspace, value.repo)
    used = len(receipts(workspace, run))
    if used >= MAX_CALLS:
        raise ValueError(f"this run has made all {MAX_CALLS} run_tests calls: submit from the results so far")
    folder = bisect_folder(workspace) / run / "tree"
    results = []
    for position in positions:
        status, failing = test_commit(history, position, folder)
        commit = history["commits"][position - 1]["id"]
        results.append(CommitResult(position=position, id=commit, status=status, failing_test=failing))
    append_receipt(
        workspace,
        run,
        {
            "call": used + 1,
            "run": run,
            "repo": value.repo.value,
            "history_sha256": history_sha256(value.repo),
            "results": [{"position": r.position, "id": r.id, "status": r.status.value} for r in results],
        },
    )
    return RunOutput(results=results, calls_used=used + 1, calls_left=MAX_CALLS - used - 1)
