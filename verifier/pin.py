from .checks import COMMIT_ID, SHA256, result, table_sha256, truth_problem


def verify_input(value):
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    if output_value.repo is not input_value.repo:
        return result(False, f"the table is for {output_value.repo.value}, not {input_value.repo.value}")
    if len(output_value.ids) != len(output_value.statuses):
        return result(False, "the table has a different number of ids and statuses")
    if len(set(output_value.ids)) != len(output_value.ids) or not all(map(COMMIT_ID.fullmatch, output_value.ids)):
        return result(False, "commit ids must be unique, 10 lowercase hex digits")
    if not SHA256.fullmatch(output_value.history_sha256):
        return result(False, "history_sha256 is not a sha256")
    if output_value.table_sha256 != table_sha256(output_value.ids, output_value.statuses):
        return result(False, "table_sha256 does not match the ids and statuses")
    problem = truth_problem(output_value.statuses)
    if problem:
        return result(False, problem)
    return result(True, "the table is a single-regression history", commits=len(output_value.ids))
