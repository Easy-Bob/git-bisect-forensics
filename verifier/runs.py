"""run_tests' checks: its positions, and that its output is the receipt it wrote."""

from contract import Status

from .checks import MAX_CALLS, MAX_POSITIONS, latest_run, read_receipts, receipts_problem, result


def verify_input(value):
    positions = value.positions
    if not 1 <= len(positions) <= MAX_POSITIONS:
        return result(False, f"run_tests takes 1 to {MAX_POSITIONS} positions")
    if len(set(positions)) != len(positions):
        return result(False, "a position is asked twice")
    if min(positions) < 1:
        return result(False, "positions start at 1")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    results = output_value.results
    if [item.position for item in results] != input_value.positions:
        return result(False, "results must answer the positions asked, in order")
    if any(item.status is Status.BAD and not item.failing_test for item in results):
        return result(False, "a bad result must name its failing test")
    if output_value.calls_used + output_value.calls_left != MAX_CALLS:
        return result(False, f"calls_used and calls_left must add up to {MAX_CALLS}")
    latest = latest_run(workspace)
    lines = read_receipts(workspace, latest["run"]) if latest else None
    if not lines:
        return result(False, "run_tests wrote no receipt")
    problem = receipts_problem(lines, latest["run"], input_value.repo.value)
    if problem:
        return result(False, problem)
    last = lines[-1]
    receipted = [(item["position"], item["id"], item["status"]) for item in last["results"]]
    if last["call"] != output_value.calls_used or receipted != [(r.position, r.id, r.status.value) for r in results]:
        return result(False, "the output is not the receipt run_tests wrote for this call")
    return result(True, "the results are receipted", call=last["call"])
