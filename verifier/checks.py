"""Checks shared by the tool verifiers. Pure functions of their arguments and the files on disk."""

import hashlib
import json
import re
from pathlib import Path

from contract import Status

COMMIT_ID = re.compile(r"^[0-9a-f]{10}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_CALLS = 3
MAX_POSITIONS = 7


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def table_sha256(ids, statuses):
    """The digest pin_truth gives its table: the ids and statuses, oldest first."""
    rows = [[commit, status.value] for commit, status in zip(ids, statuses, strict=True)]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def line_sha256(body):
    """A receipt line's own digest: the line without its sha256 field, as src/plugin/runs.py writes it."""
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def truth_problem(statuses):
    """What makes ``statuses`` no single-regression history, or None: the oldest commit good, the newest
    bad, and no good commit after a bad one (skip commits may be anywhere)."""
    if len(statuses) < 2:
        return "a history needs at least 2 commits"
    if statuses[0] is not Status.GOOD or statuses[-1] is not Status.BAD:
        return "the oldest commit must be good and the newest bad"
    first_bad = statuses.index(Status.BAD)
    if Status.GOOD in statuses[first_bad:]:
        return f"a good commit follows the first bad one (position {first_bad + 1})"
    return None


def answer(ids, statuses):
    """The right answer from a table: (first_bad, last_good, skipped_between), as ids."""
    first = statuses.index(Status.BAD)
    last = max(position for position in range(first) if statuses[position] is Status.GOOD)
    return ids[first], ids[last], [ids[p] for p in range(last + 1, first) if statuses[p] is Status.SKIP]


def latest_run(workspace):
    """The run git_log started last in ``workspace`` as {"run", "repo"}, or None."""
    index = Path(workspace) / "bisect" / "runs.jsonl"
    lines = index.read_text().splitlines() if index.is_file() else []
    return json.loads(lines[-1]) if lines else None


def read_receipts(workspace, run):
    """A run's receipt lines, parsed, or None when it has none."""
    path = Path(workspace) / "bisect" / run / "receipts.jsonl"
    if not path.is_file():
        return None
    return [json.loads(line) for line in path.read_text().splitlines()]


def receipts_problem(lines, run, repo):
    """What breaks a run's receipt chain, or None."""
    previous = ""
    for number, line in enumerate(lines, start=1):
        body = dict(line)
        digest = body.pop("sha256", None)
        if digest != line_sha256(body):
            return f"receipt {number} was altered after run_tests wrote it: it no longer matches its own sha256"
        if body.get("prev") != previous:
            return f"receipt {number} does not follow receipt {number - 1}: a receipt was dropped or reordered"
        if body.get("call") != number or body.get("run") != run or body.get("repo") != repo:
            return f"receipt {number} is not call {number} of run {run} for {repo}"
        previous = digest
    return None
