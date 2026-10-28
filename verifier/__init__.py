"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import log, pin, runs, show, task

TOOLS = {
    Tool.PIN_TRUTH: pin,
    Tool.GIT_LOG: log,
    Tool.SHOW_COMMIT: show,
    Tool.RUN_TESTS: runs,
}

# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {
    Task.BISECT: task.verify_task,
}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
