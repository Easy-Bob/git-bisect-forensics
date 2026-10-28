from .checks import COMMIT_ID, result


def verify_input(value):
    if value.position < 1:
        return result(False, "position must be 1 or more")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    if output_value.position != input_value.position:
        return result(False, f"shows position {output_value.position}, not {input_value.position}")
    if not COMMIT_ID.fullmatch(output_value.id):
        return result(False, f"{output_value.id!r} is not a commit id")
    if not output_value.files_changed or output_value.files_changed != sorted(output_value.files_changed):
        return result(False, "files_changed must list the commit's files, sorted")
    return result(True, "the commit is shown", files=len(output_value.files_changed))
