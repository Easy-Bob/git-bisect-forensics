"""show_commit: one commit's message and its unified diff against its parent. It runs nothing."""

from __future__ import annotations

import difflib
from pathlib import Path

from contract import ShowInput, ShowOutput
from plugin.history import load_history, tree_at
from plugin.log import first_line

MAX_DIFF = 6000


def commit_diff(before: dict[str, str], after: dict[str, str], paths: list[str]) -> str:
    chunks = []
    for path in paths:
        old, new = before.get(path), after.get(path)
        chunks.extend(
            difflib.unified_diff(
                (old or "").splitlines(keepends=True),
                (new or "").splitlines(keepends=True),
                fromfile="/dev/null" if old is None else f"a/{path}",
                tofile="/dev/null" if new is None else f"b/{path}",
            )
        )
    return "".join(chunks)[:MAX_DIFF]


def show_commit(value: ShowInput, workspace: Path) -> ShowOutput:
    history = load_history(value.repo)
    after = tree_at(history, value.position)
    before = tree_at(history, value.position - 1) if value.position > 1 else {}
    commit = history["commits"][value.position - 1]
    paths = sorted(commit["changes"])
    return ShowOutput(
        position=value.position,
        id=commit["id"],
        message=first_line(commit["message"]),
        files_changed=paths,
        diff=commit_diff(before, after, paths),
    )
