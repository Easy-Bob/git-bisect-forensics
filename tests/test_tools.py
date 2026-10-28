from __future__ import annotations

import json
from pathlib import Path

import pytest

from contract import LogInput, Repo, RunInput, ShowInput, Status
from plugin import git_log, run_tests, show_commit
from plugin.history import load_history, tree_at
from plugin.runs import bisect_folder, latest_run, receipts
from plugin.testrun import run_suite


def test_git_log_lists_every_commit_and_starts_a_run(tmp_path: Path) -> None:
    log = git_log(LogInput(repo=Repo.MONEYFMT), tmp_path)
    assert [commit.position for commit in log.commits] == list(range(1, 65))
    assert log.commits[0].message == "Initial import"
    run = latest_run(tmp_path, Repo.MONEYFMT)
    header = json.loads((bisect_folder(tmp_path) / run / "run.json").read_text())
    assert header["repo"] == "moneyfmt" and header["commits"] == 64
    git_log(LogInput(repo=Repo.MONEYFMT), tmp_path)
    assert latest_run(tmp_path, Repo.MONEYFMT) != run


def test_show_commit_gives_the_regressions_diff(tmp_path: Path) -> None:
    shown = show_commit(ShowInput(repo=Repo.MONEYFMT, position=37), tmp_path)
    assert shown.files_changed == ["moneyfmt/core.py"]
    assert "-    if 2 * remainder >= abs(denominator):" in shown.diff
    assert "+    if 2 * remainder > abs(denominator):" in shown.diff
    first = show_commit(ShowInput(repo=Repo.MONEYFMT, position=1), tmp_path)
    assert "--- /dev/null" in first.diff and "tests/test_core.py" in first.files_changed


@pytest.mark.parametrize("repo", list(Repo))
def test_run_tests_agrees_with_the_answer_key(repo: Repo, tmp_path: Path, pinned: dict) -> None:
    count = len(pinned[repo].statuses)
    positions = sorted({1, 2, count // 3, count // 2, count - 1, count})
    git_log(LogInput(repo=repo), tmp_path)
    out = run_tests(RunInput(repo=repo, positions=positions), tmp_path)
    assert [r.status for r in out.results] == [pinned[repo].statuses[p - 1] for p in positions]
    assert [r.id for r in out.results] == [pinned[repo].ids[p - 1] for p in positions]
    assert all(bool(r.failing_test) == (r.status is Status.BAD) for r in out.results)
    assert (out.calls_used, out.calls_left) == (1, 2)


def test_run_tests_names_the_failing_test(tmp_path: Path) -> None:
    git_log(LogInput(repo=Repo.MONEYFMT), tmp_path)
    [bad] = run_tests(RunInput(repo=Repo.MONEYFMT, positions=[37]), tmp_path).results
    assert bad.failing_test.startswith("tests.test_core.CoreTest.test_round_half_up: AssertionError")


def test_run_tests_receipts_each_call_and_allows_three(tmp_path: Path) -> None:
    git_log(LogInput(repo=Repo.CSVSUM), tmp_path)
    for call in range(1, 4):
        out = run_tests(RunInput(repo=Repo.CSVSUM, positions=[call]), tmp_path)
        assert out.calls_used == call
    lines = receipts(tmp_path, latest_run(tmp_path, Repo.CSVSUM))
    assert [line["call"] for line in lines] == [1, 2, 3]
    assert lines[1]["prev"] == lines[0]["sha256"] and lines[0]["prev"] == ""
    with pytest.raises(ValueError, match="all 3 run_tests calls"):
        run_tests(RunInput(repo=Repo.CSVSUM, positions=[4]), tmp_path)


@pytest.mark.parametrize(
    ("positions", "message"),
    [
        ([], "1 to 7 positions"),
        ([1, 2, 3, 4, 5, 6, 7, 8], "1 to 7 positions"),
        ([3, 3], "asked twice"),
        ([0], "positions run 1 to 33"),
        ([34], "positions run 1 to 33"),
    ],
)
def test_run_tests_refuses_bad_positions(tmp_path: Path, positions: list[int], message: str) -> None:
    git_log(LogInput(repo=Repo.CSVSUM), tmp_path)
    with pytest.raises(ValueError, match=message):
        run_tests(RunInput(repo=Repo.CSVSUM, positions=positions), tmp_path)


def test_run_tests_needs_a_run_for_its_repo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="call git_log first"):
        run_tests(RunInput(repo=Repo.CSVSUM, positions=[1]), tmp_path)
    git_log(LogInput(repo=Repo.SLUGIFY), tmp_path)
    with pytest.raises(ValueError, match="the latest run is for slugify"):
        run_tests(RunInput(repo=Repo.CSVSUM, positions=[1]), tmp_path)


def test_a_commit_that_does_not_load_is_skip(tmp_path: Path) -> None:
    history = load_history(Repo.SLUGIFY)
    assert "def truncate(text, limit:" in tree_at(history, 18)["slugify/core.py"]
    git_log(LogInput(repo=Repo.SLUGIFY), tmp_path)
    out = run_tests(RunInput(repo=Repo.SLUGIFY, positions=[18, 19]), tmp_path)
    assert [r.status for r in out.results] == [Status.SKIP, Status.SKIP]


def test_a_test_that_hangs_or_kills_the_runner_is_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plugin import testrun

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    test = "import os, time, unittest\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        {}\n"
    (tmp_path / "tests" / "test_x.py").write_text(test.format("os._exit(0)"))
    assert run_suite(tmp_path) == (Status.SKIP, "")
    monkeypatch.setattr(testrun, "TIMEOUT", 0.5)
    (tmp_path / "tests" / "test_x.py").write_text(test.format("time.sleep(5)"))
    assert run_suite(tmp_path) == (Status.SKIP, "")
