"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    PIN_TRUTH = "pin_truth"
    GIT_LOG = "git_log"
    SHOW_COMMIT = "show_commit"
    RUN_TESTS = "run_tests"


class Task(Enum):
    BISECT = "bisect"


class Repo(Enum):
    MONEYFMT = "moneyfmt"
    DATEPARSE = "dateparse"
    INIPARSE = "iniparse"
    SLUGIFY = "slugify"
    CSVSUM = "csvsum"


class Status(Enum):
    GOOD = "good"
    BAD = "bad"
    SKIP = "skip"


REPO = "The bundled project whose history is searched"
POSITION = "A commit's place in the history, 1 = the oldest (its tests pass) to N = the newest (its tests fail)"
COMMIT_ID = "A commit id: 10 lowercase hex digits, as git_log and run_tests give it"
STATUS = "good: every test passes; bad: a test fails; skip: the commit cannot be tested (it does not load)"


@dataclass
class BisectInput(Output):
    repo: Annotated[Repo, REPO]


@dataclass
class PinOutput(Output):
    repo: Annotated[Repo, REPO]
    ids: Annotated[list[str], "Every commit's id, oldest first"]
    statuses: Annotated[list[Status], "Every commit's test status, oldest first"]
    history_sha256: Annotated[str, "The sha256 of the bundled history the statuses come from"]
    table_sha256: Annotated[str, "The sha256 of the ids and statuses, as checks.table_sha256 computes it"]


@dataclass
class LogInput(Output):
    repo: Annotated[Repo, REPO]


@dataclass
class Commit(Output):
    position: Annotated[int, POSITION]
    id: Annotated[str, COMMIT_ID]
    date: Annotated[str, "When it was committed, YYYY-MM-DDTHH:MM:SSZ"]
    author: Annotated[str, "Who committed it"]
    message: Annotated[str, "Its commit message's first line"]


@dataclass
class LogOutput(Output):
    repo: Annotated[Repo, REPO]
    commits: Annotated[list[Commit], "Every commit, oldest first: positions 1 to N"]


@dataclass
class ShowInput(Output):
    repo: Annotated[Repo, REPO]
    position: Annotated[int, POSITION]


@dataclass
class ShowOutput(Output):
    position: Annotated[int, POSITION]
    id: Annotated[str, COMMIT_ID]
    message: Annotated[str, "Its commit message's first line"]
    files_changed: Annotated[list[str], "The files the commit changes, sorted"]
    diff: Annotated[str, "Its unified diff against its parent, cut at 6000 characters"]


@dataclass
class RunInput(Output):
    repo: Annotated[Repo, REPO]
    positions: Annotated[list[int], "1 to 7 distinct positions from git_log to run the tests at"]


@dataclass
class CommitResult(Output):
    position: Annotated[int, POSITION]
    id: Annotated[str, COMMIT_ID]
    status: Annotated[Status, STATUS]
    failing_test: Annotated[str, "The first failing test and its error's last line; empty unless bad"]


@dataclass
class RunOutput(Output):
    results: Annotated[list[CommitResult], "One result per position, in the order asked"]
    calls_used: Annotated[int, "How many run_tests calls this run has made, this one included"]
    calls_left: Annotated[int, "How many run_tests calls this run has left"]


@dataclass
class BisectOutput(Output):
    repo: Annotated[Repo, REPO]
    first_bad: Annotated[str, "The id of the oldest commit whose tests fail, as run_tests gave it"]
    last_good: Annotated[str, "The id of the newest commit before it whose tests pass, as run_tests gave it"]
    skipped_between: Annotated[list[str], "The ids of the skip commits between last_good and first_bad, oldest first"]


TOOLS = {
    Tool.PIN_TRUTH: (BisectInput, PinOutput),
    Tool.GIT_LOG: (LogInput, LogOutput),
    Tool.SHOW_COMMIT: (ShowInput, ShowOutput),
    Tool.RUN_TESTS: (RunInput, RunOutput),
}

TASKS = {Task.BISECT: (BisectInput, BisectOutput)}
