"""git_log: a repo's commits, oldest first. Each call starts a new bisect run in the workspace."""

from __future__ import annotations

from pathlib import Path

from contract import Commit, LogInput, LogOutput
from plugin.history import history_sha256, load_history
from plugin.runs import start_run


def first_line(message: str) -> str:
    return message.splitlines()[0] if message else ""


def git_log(value: LogInput, workspace: Path) -> LogOutput:
    history = load_history(value.repo)
    start_run(workspace, value.repo, history_sha256(value.repo), len(history["commits"]))
    commits = [
        Commit(
            position=position,
            id=commit["id"],
            date=commit["date"],
            author=commit["author"],
            message=first_line(commit["message"]),
        )
        for position, commit in enumerate(history["commits"], start=1)
    ]
    return LogOutput(repo=value.repo, commits=commits)
