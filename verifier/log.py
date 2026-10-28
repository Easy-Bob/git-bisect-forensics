import json
from pathlib import Path

from .checks import COMMIT_ID, latest_run, result


def verify_input(value):
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    commits = output_value.commits
    if output_value.repo is not input_value.repo:
        return result(False, f"the log is for {output_value.repo.value}, not {input_value.repo.value}")
    if [commit.position for commit in commits] != list(range(1, len(commits) + 1)):
        return result(False, "positions must run 1 to N, oldest first")
    ids = [commit.id for commit in commits]
    if len(set(ids)) != len(ids) or not all(map(COMMIT_ID.fullmatch, ids)):
        return result(False, "commit ids must be unique, 10 lowercase hex digits")
    latest = latest_run(workspace)
    if latest is None or latest["repo"] != input_value.repo.value:
        return result(False, f"git_log did not start a run for {input_value.repo.value} in the workspace")
    header = Path(workspace) / "bisect" / latest["run"] / "run.json"
    if not header.is_file() or json.loads(header.read_text()).get("commits") != len(commits):
        return result(False, "the run's run.json does not record this history")
    return result(True, "the log is well formed and its run started", commits=len(commits), run=latest["run"])
