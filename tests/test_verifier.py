from __future__ import annotations

import ast
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
from contract import TOOLS, BisectInput, LogInput, Repo, RunInput, ShowInput, Tool
from plugin import git_log, run_tests, show_commit

# NanoAgent's sandbox lets a verifier import only these, contract and its own package.
ALLOWED_IMPORTS = {
    "__future__", "collections", "dataclasses", "decimal", "difflib", "enum", "fractions", "functools",
    "hashlib", "itertools", "json", "math", "operator", "pathlib", "re", "statistics", "string",
    "textwrap", "typing", "unicodedata",
}  # fmt: skip
FORBIDDEN_NAMES = {"__import__", "compile", "eval", "exec", "getattr", "globals", "open", "setattr", "vars"}


# The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
def verify_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


def verify_output(tool: str, given: dict, made, workspace: Path) -> dict:
    given_class, made_class = TOOLS[Tool(tool)]
    return verifier.verify_output(
        tool, build_output(given, given_class), build_output(plain_output(made), made_class), str(workspace)
    )


def test_the_verifier_imports_only_what_the_sandbox_allows() -> None:
    for path in Path(verifier.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in ALLOWED_IMPORTS for alias in node.names), path.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module.split(".")[0] in ALLOWED_IMPORTS | {"contract"}, path.name
            elif isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_NAMES, f"{path.name} uses {node.id}"


def test_checks_what_the_types_cannot_say() -> None:
    assert verify_input("run_tests", {"repo": "moneyfmt", "positions": [1, 2]})["valid"] is True
    assert verify_input("run_tests", {"repo": "moneyfmt", "positions": []})["valid"] is False
    assert verify_input("run_tests", {"repo": "moneyfmt", "positions": list(range(1, 9))})["valid"] is False
    assert verify_input("run_tests", {"repo": "moneyfmt", "positions": [2, 2]})["valid"] is False
    assert verify_input("run_tests", {"repo": "moneyfmt", "positions": [0]})["valid"] is False
    assert verify_input("show_commit", {"repo": "moneyfmt", "position": 0})["valid"] is False
    assert verify_input("git_log", {"repo": "csvsum"})["valid"] is True


def test_tool_outputs_are_judged_against_the_workspace(tmp_path: Path) -> None:
    given = {"repo": "csvsum"}
    log = git_log(LogInput(repo=Repo.CSVSUM), tmp_path)
    assert verify_output("git_log", given, log, tmp_path)["valid"] is True
    assert verify_output("git_log", given, log, tmp_path / "elsewhere")["valid"] is False

    asked = {"repo": "csvsum", "positions": [16, 17]}
    ran = run_tests(RunInput(repo=Repo.CSVSUM, positions=[16, 17]), tmp_path)
    assert verify_output("run_tests", asked, ran, tmp_path)["valid"] is True
    assert verify_output("run_tests", asked | {"positions": [17, 16]}, ran, tmp_path)["valid"] is False
    ran.results[0].status, ran.results[0].failing_test = ran.results[1].status, ran.results[1].failing_test
    assert "not the receipt" in verify_output("run_tests", asked, ran, tmp_path)["message"]

    shown = show_commit(ShowInput(repo=Repo.CSVSUM, position=17), tmp_path)
    assert verify_output("show_commit", {"repo": "csvsum", "position": 17}, shown, tmp_path)["valid"] is True
    assert verify_output("show_commit", {"repo": "csvsum", "position": 16}, shown, tmp_path)["valid"] is False


def test_the_answer_key_is_checked_as_a_single_regression_history(tmp_path: Path, pinned: dict) -> None:
    key = pinned[Repo.SLUGIFY]
    assert verify_output("pin_truth", {"repo": "slugify"}, key, tmp_path)["valid"] is True
    assert verify_output("pin_truth", {"repo": "csvsum"}, key, tmp_path)["valid"] is False
    flipped = build_output(plain_output(key), TOOLS[Tool.PIN_TRUTH][1])
    flipped.statuses[-1] = flipped.statuses[0]
    assert "table_sha256" in verify_output("pin_truth", {"repo": "slugify"}, flipped, tmp_path)["message"]


def test_the_task_input_is_the_reference_tools() -> None:
    assert TOOLS[Tool.PIN_TRUTH][0] is BisectInput
