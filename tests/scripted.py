"""A scripted bisect run: the case's tool calls through the real tools, its submission, then the verifier.

No model runs. A case (tests/cases/<name>.json) gives the repo, each run_tests call's positions, the
submission (positions, turned into the ids the history gives them, or ids as strings), an optional
tamper applied before judging, and the verdict it expects.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
from contract import BisectInput, BisectOutput, LogInput, Repo, RunInput, Status
from plugin import git_log, run_tests
from plugin.history import load_history
from plugin.runs import bisect_folder, latest_run, line_sha256

CASES = Path(__file__).parent / "cases"


def commit_id(repo: Repo, value: int | str) -> str:
    """A position's id in ``repo``'s history; a string is taken as an id already."""
    return value if isinstance(value, str) else load_history(repo)["commits"][value - 1]["id"]


def receipts_path(workspace: Path, repo: Repo) -> Path:
    return bisect_folder(workspace) / latest_run(workspace, repo) / "receipts.jsonl"


def rewrite(path: Path, lines: list[dict], *, reseal: bool) -> None:
    """Write receipt lines back; ``reseal`` recomputes each line's chain as a forger who knows it would."""
    previous = ""
    out = []
    for line in lines:
        body = {key: value for key, value in line.items() if key != "sha256"}
        if reseal:
            body["prev"] = previous
            line = body | {"sha256": line_sha256(body)}
            previous = line["sha256"]
        out.append(json.dumps(line, sort_keys=True))
    path.write_text("".join(text + "\n" for text in out))


def tamper(kind: str, workspace: Path, repo: Repo) -> None:
    if kind == "edit-receipt":
        path = receipts_path(workspace, repo)
        lines = [json.loads(text) for text in path.read_text().splitlines()]
        lines[0]["results"][0]["status"] = "bad" if lines[0]["results"][0]["status"] == "good" else "good"
        rewrite(path, lines, reseal=False)
    elif kind == "forge-receipt":
        path = receipts_path(workspace, repo)
        lines = [json.loads(text) for text in path.read_text().splitlines()]
        lines[0]["results"][0]["status"] = "bad" if lines[0]["results"][0]["status"] == "good" else "good"
        rewrite(path, lines, reseal=True)
    elif kind == "drop-receipt":
        path = receipts_path(workspace, repo)
        lines = [json.loads(text) for text in path.read_text().splitlines()]
        rewrite(path, lines[1:], reseal=False)
    elif kind == "new-run":
        git_log(LogInput(repo=repo), workspace)
    elif kind == "other-repo-run":
        other = next(item for item in Repo if item is not repo)
        git_log(LogInput(repo=other), workspace)
    elif kind != "altered-answer-key":
        raise ValueError(f"unknown tamper {kind!r}")


def run_case(case: dict, workspace: Path, pinned: dict) -> dict:
    repo = Repo(case["repo"])
    if case.get("log", True):
        git_log(LogInput(repo=repo), workspace)
    for positions in case["calls"]:
        run_tests(RunInput(repo=repo, positions=positions), workspace)
    if case.get("tamper"):
        tamper(case["tamper"], workspace, repo)
    submit = case["submit"]
    output = BisectOutput(
        repo=Repo(submit.get("repo", repo.value)),
        first_bad=commit_id(repo, submit["first_bad"]),
        last_good=commit_id(repo, submit["last_good"]),
        skipped_between=[commit_id(repo, value) for value in submit["skipped_between"]],
    )
    reference = pinned[repo]
    if case.get("tamper") == "altered-answer-key":
        statuses = list(reference.statuses)
        statuses[0] = Status.SKIP if statuses[0] is Status.GOOD else Status.GOOD
        reference = replace(reference, statuses=statuses)
    # The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
    return verifier.verify_task(
        "bisect",
        build_output({"repo": repo.value}, BisectInput),
        build_output(plain_output(output), BisectOutput),
        reference,
        str(workspace),
    )


def load_cases() -> list[dict]:
    return [json.loads(path.read_text()) | {"name": path.stem} for path in sorted(CASES.glob("*.json"))]
