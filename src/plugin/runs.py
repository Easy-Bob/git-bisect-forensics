"""A bisect run's folder in the workspace: which run is the latest, and its receipts of run_tests calls.

``bisect/runs.jsonl`` lists every run git_log started, oldest first. A run's folder,
``bisect/<run>/``, holds ``run.json`` (its repo and history) and ``receipts.jsonl``: one line per
run_tests call, each line carrying its own sha256 and the previous line's, so an edited, dropped or
reordered line shows.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from contract import Repo

MAX_CALLS = 3


def bisect_folder(workspace: Path) -> Path:
    return workspace / "bisect"


def start_run(workspace: Path, repo: Repo, history_sha256: str, commits: int) -> str:
    run = secrets.token_hex(8)
    folder = bisect_folder(workspace) / run
    folder.mkdir(parents=True)
    header = {"run": run, "repo": repo.value, "history_sha256": history_sha256, "commits": commits}
    (folder / "run.json").write_text(json.dumps(header, sort_keys=True) + "\n")
    with (bisect_folder(workspace) / "runs.jsonl").open("a") as runs:
        runs.write(json.dumps({"run": run, "repo": repo.value}, sort_keys=True) + "\n")
    return run


def latest_run(workspace: Path, repo: Repo) -> str:
    """The run git_log started last in this workspace; it must be for ``repo``."""
    index = bisect_folder(workspace) / "runs.jsonl"
    lines = index.read_text().splitlines() if index.exists() else []
    if not lines:
        raise ValueError("no run has started: call git_log first")
    last = json.loads(lines[-1])
    if last["repo"] != repo.value:
        raise ValueError(f"the latest run is for {last['repo']}, not {repo.value}: call git_log for {repo.value} first")
    return last["run"]


def receipts(workspace: Path, run: str) -> list[dict]:
    path = bisect_folder(workspace) / run / "receipts.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def line_sha256(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def append_receipt(workspace: Path, run: str, body: dict) -> None:
    """Append one call's receipt: ``body`` with the previous line's sha256 and its own."""
    earlier = receipts(workspace, run)
    body = body | {"prev": earlier[-1]["sha256"] if earlier else ""}
    line = json.dumps(body | {"sha256": line_sha256(body)}, sort_keys=True)
    with (bisect_folder(workspace) / run / "receipts.jsonl").open("a") as out:
        out.write(line + "\n")
