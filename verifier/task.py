"""The bisect task's check: the submitted commits are the right ones, and the agent's own receipted
run_tests calls prove them.

Nine checks, in order. 1 to 3 guard the evidence: when one fails nothing after it is judged. Any of
1 to 6 failing scores 0; otherwise any of 7 to 9 failing scores 0.5. Valid only when all nine hold.
"""

from contract import Status

from .checks import (
    MAX_CALLS,
    MAX_POSITIONS,
    answer,
    latest_run,
    read_receipts,
    receipts_problem,
    result,
    table_sha256,
    truth_problem,
)

ZEROES = {"truth-integrity", "receipts-integrity", "receipts-agree", "submitted-shape", "budget", "first-bad-correct"}
CHECKS = [
    "truth-integrity",
    "receipts-integrity",
    "receipts-agree",
    "submitted-shape",
    "budget",
    "first-bad-correct",
    "last-good-correct",
    "skipped-exact",
    "proven",
]


def verdict(failures, **details):
    """The task's result from the failed checks, as [(check, why)] in check order."""
    if not failures:
        return result(True, f"All {len(CHECKS)} checks hold.", **details)
    score = 0.0 if any(check in ZEROES for check, _ in failures) else 0.5
    check, why = failures[0]
    more = f" (+{len(failures) - 1} more)" if len(failures) > 1 else ""
    return result(False, f"{check}: {why}{more}", score=score, failed=[name for name, _ in failures], **details)


def truth(arguments, reference):
    if reference is None:
        return "no answer key was pinned"
    if reference.repo is not arguments.repo:
        return f"the answer key is for {reference.repo.value}, not {arguments.repo.value}"
    if len(reference.ids) != len(reference.statuses):
        return "the answer key has a different number of ids and statuses"
    if reference.table_sha256 != table_sha256(reference.ids, reference.statuses):
        return "the answer key was altered: its table no longer matches its sha256"
    return truth_problem(reference.statuses)


def receipts(arguments, workspace):
    """(the latest run's receipt lines, None), or (None, why they cannot be trusted)."""
    repo = arguments.repo.value
    latest = latest_run(workspace)
    if latest is None:
        return None, "no run was started: git_log was never called"
    if latest["repo"] != repo:
        return None, f"the latest run is for {latest['repo']}, not {repo}"
    lines = read_receipts(workspace, latest["run"])
    if not lines:
        return None, f"run {latest['run']} has no run_tests receipts: the agent never ran the tests"
    problem = receipts_problem(lines, latest["run"], repo)
    return (None, problem) if problem else (lines, None)


def disagreement(lines, reference):
    ids, statuses = reference.ids, reference.statuses
    for line in lines:
        if line.get("history_sha256") != reference.history_sha256:
            return f"call {line['call']} ran on another history than the answer key's"
        for item in line["results"]:
            position = item["position"]
            if not 1 <= position <= len(ids) or ids[position - 1] != item["id"]:
                return (
                    f"call {line['call']} names commit {item['id']} at position {position}, which the history does not"
                )
            if statuses[position - 1].value != item["status"]:
                expected = statuses[position - 1].value
                return f"call {line['call']} saw position {position} {item['status']}; the answer key has it {expected}"
    return None


def shape(arguments, output, ids):
    if output.repo is not arguments.repo:
        return f"the submission is for {output.repo.value}, not {arguments.repo.value}"
    named = [output.first_bad, output.last_good, *output.skipped_between]
    unknown = [commit for commit in named if commit not in ids]
    if unknown:
        return f"{unknown[0]!r} is not a commit of {arguments.repo.value} (copy ids exactly as run_tests gave them)"
    if len(set(named)) != len(named):
        return "a commit is named twice among first_bad, last_good and skipped_between"
    return None


def budget(lines):
    tested = sum(len(line["results"]) for line in lines)
    if len(lines) > MAX_CALLS or tested > MAX_CALLS * MAX_POSITIONS:
        return f"{len(lines)} run_tests calls testing {tested} commits; at most {MAX_CALLS} calls of {MAX_POSITIONS}"
    return None


def unproven(output, ids, lines):
    """What the agent's own receipts do not show of its answer, or None."""
    seen = {item["id"]: item["status"] for line in lines for item in line["results"]}
    if seen.get(output.first_bad) != Status.BAD.value:
        return f"first_bad {output.first_bad} was never tested bad: run_tests must show it"
    if seen.get(output.last_good) != Status.GOOD.value:
        return f"last_good {output.last_good} was never tested good: run_tests must show it"
    low, high = ids.index(output.last_good), ids.index(output.first_bad)
    untested = [ids[p] for p in range(low + 1, high) if seen.get(ids[p]) != Status.SKIP.value]
    if untested:
        return f"{untested[0]} lies between last_good and first_bad but was never tested skip"
    return None


def verify_task(arguments, output, reference, workspace):
    """``output``: a contract BisectOutput; ``reference``: pin_truth's PinOutput."""
    problem = truth(arguments, reference)
    if problem:
        return verdict([("truth-integrity", problem)])
    lines, problem = receipts(arguments, workspace)
    if problem:
        return verdict([("receipts-integrity", problem)])
    problem = disagreement(lines, reference)
    if problem:
        return verdict([("receipts-agree", problem)])

    ids = reference.ids
    first_bad, last_good, skipped = answer(ids, reference.statuses)
    details = {"first_bad": first_bad, "last_good": last_good, "skipped_between": skipped, "calls": len(lines)}
    failures = []
    problem = shape(arguments, output, ids)
    if problem:
        failures.append(("submitted-shape", problem))
    problem = budget(lines)
    if problem:
        failures.append(("budget", problem))
    if output.first_bad != first_bad:
        failures.append(
            ("first-bad-correct", f"first_bad is {output.first_bad}; the first commit whose tests fail is {first_bad}")
        )
    if output.last_good != last_good:
        failures.append(
            ("last-good-correct", f"last_good is {output.last_good}; the newest good commit before it is {last_good}")
        )
    if output.skipped_between != skipped:
        failures.append(
            ("skipped-exact", f"skipped_between is {output.skipped_between}; the skip commits between are {skipped}")
        )
    if not any(check == "submitted-shape" for check, _ in failures):
        problem = unproven(output, ids, lines)
        if problem:
            failures.append(("proven", problem))
    return verdict(failures, **details)
