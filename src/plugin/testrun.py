"""Run a commit's tests: the one function pin_truth and run_tests both judge commits with."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from contract import Status
from plugin.history import materialize, tree_at

TIMEOUT = 10.0
# Runs in the commit's folder, in a fresh isolated interpreter (-I: no environment, user site or
# current folder on the path; -B: no bytecode written). A test module that does not load (a syntax or
# import error) makes the commit untestable, skip; a failing or erroring test makes it bad.
RUNNER = """
import io, json, unittest
loader = unittest.TestLoader()
suite = loader.discover("tests", top_level_dir=".")
if loader.errors or suite.countTestCases() == 0:
    print(json.dumps({"status": "skip", "failing_test": ""}))
else:
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    failed = sorted(result.failures + result.errors, key=lambda item: item[0].id())
    if failed:
        test, trace = failed[0]
        last = trace.strip().splitlines()[-1]
        print(json.dumps({"status": "bad", "failing_test": f"{test.id()}: {last}"[:200]}))
    else:
        print(json.dumps({"status": "good", "failing_test": ""}))
"""


def run_suite(folder: Path) -> tuple[Status, str]:
    """The status of the tests in ``folder``, and the first failing test when it is bad."""
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-B", "-c", RUNNER],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            # Failing tests exit 1 too: the runner's verdict line, not its exit code, decides.
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Status.SKIP, ""
    lines = done.stdout.strip().splitlines()
    if not lines:
        # The runner itself died (a test exited the interpreter): the commit cannot be judged.
        return Status.SKIP, ""
    verdict = json.loads(lines[-1])
    return Status(verdict["status"]), verdict["failing_test"]


def test_commit(history: dict, position: int, folder: Path) -> tuple[Status, str]:
    """Write the commit at ``position`` into ``folder`` and run its tests there."""
    materialize(tree_at(history, position), folder)
    return run_suite(folder)


# Not a test for pytest to collect.
test_commit.__test__ = False
