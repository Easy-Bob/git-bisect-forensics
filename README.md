# Git Bisect Forensics

A `nanoagent.plugin/v0001` plugin. Its task, `bisect`, gives an agent a small
Python project's history where the oldest commit passes its tests and the
newest fails. The agent must find the first commit whose tests fail, with a
budget of 3 test calls of 7 commits each, and back its answer with its own
test runs. A rule-based verifier checks the answer against an answer key that
tested every commit, and checks the agent's receipted test runs prove it.

## Tools

| Tool | Does | Code |
|---|---|---|
| `pin_truth` | The answer key. It runs the tests of every commit of the repo's history in a scratch workspace and pins each commit's status (good, bad or skip), with a sha256 of the history and of the table | `src/plugin/pin.py` |
| `git_log` | The repo's commits, oldest first: position, id, date, author and message. Each call starts a new bisect run in `bisect/<run>/` | `src/plugin/log.py` |
| `show_commit` | One commit's message, changed files and unified diff against its parent. It runs nothing | `src/plugin/show.py` |
| `run_tests` | The repo's tests at up to 7 commits by position, each good, bad (with its first failing test) or skip, at most 3 calls per run. Each call appends a receipt to `bisect/<run>/receipts.jsonl` | `src/plugin/run_tests.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `bisect` | Finds the first commit whose tests fail and submits it with the newest good commit before it and the skip commits between them | `agent`, with `git_log`, `show_commit` and `run_tests`; reference `pin_truth` |

## The task

Before the agent starts, NanoAgent runs `pin_truth` with the task input in a
scratch workspace the agent never sees, and pins its output. The agent then
calls `git_log`, `run_tests` (at most 3 times, 7 commits each) and `submit`.
Two calls of 7 narrow 64 commits to one (64, then 8, then 1), which fits the
hosted agent's 6 steps; the third call is spare, for skips and boundaries.

A commit is tested by writing its files into the run's `tree/` folder and
running `python -I -B` with `unittest` discovery there, with a 10 s timeout.
Every test passing is `good`; a failing or erroring test is `bad`; a test
module that does not load (a syntax or import error), no tests, a timeout or
a dead interpreter is `skip`, as with `git bisect skip`.

### The repos

The histories are bundled in `src/plugin/data/<repo>.json`, each commit with
the files it changes. `src/plugin/tools_dev/build_histories.py` builds them
from seeded specs and refuses a history whose commits do not test as its spec
says.

Every history is **linear** and has **one regression**:

- Linear: each commit has exactly one parent, the commit before it, so there
  are no branches or merges, and a commit's position (1 to N) orders the
  history.
- One regression: the statuses run good, then bad, and never good again after
  the first bad (`good … good bad … bad`), with skip commits anywhere. So one
  test settles a whole side: a good commit means every commit before it is
  good or skip, and a bad commit means every commit after it is bad or skip.
  This is what lets 14 tests settle 64 commits. The generator, `pin_truth`'s
  verifier and the `truth-integrity` check each refuse a history that breaks
  it.

| Repo | Commits | First bad | What it tests |
|---|---|---|---|
| `moneyfmt` | 64 | 37 | A regression in the middle |
| `dateparse` | 64 | 2 | The regression right after the root: position 1 must be tested |
| `iniparse` | 64 | 64 | HEAD is the first bad: all 3 calls are needed |
| `slugify` | 48 | 20 | Commits 18 and 19 do not load (skip); the regression hides behind them |
| `csvsum` | 33 | 17 | A good commit (16) is titled "fix rounding in totals" |

## The verifier

`verifier/task.py` runs nine checks in order. Checks 1 to 3 guard the
evidence, and when one fails nothing after it is judged.

| # | Check | Fails when | Score |
|---|---|---|---|
| 1 | `truth-integrity` | The answer key is altered (its table no longer matches its sha256), is another repo's, or is no single-regression history | 0 |
| 2 | `receipts-integrity` | No run, the latest run is another repo's, it has no receipts, or a receipt was edited, dropped or reordered | 0 |
| 3 | `receipts-agree` | A result the agent saw differs from the answer key, or came from another history | 0 |
| 4 | `submitted-shape` | The submission names another repo, a commit not in the history, or a commit twice | 0 |
| 5 | `budget` | More than 3 calls or 21 commits tested | 0 |
| 6 | `first-bad-correct` | `first_bad` is not the first commit whose tests fail | 0 |
| 7 | `last-good-correct` | `last_good` is not the newest good commit before it | 0.5 |
| 8 | `skipped-exact` | `skipped_between` is not exactly the skip commits between them | 0.5 |
| 9 | `proven` | The receipts do not show `first_bad` bad, `last_good` good and every commit between skip | 0.5 |

Valid, and score 1.0, only when all nine hold. The message names the first
failing check and why, and how many more fail, e.g. `proven: first_bad
3f9a1c07e2 was never tested bad: run_tests must show it`.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none here)
├── src/plugin/      # the MCP server (__main__.py, its IMPLEMENTATIONS table), the tools, data/ and tools_dev/
├── tests/           # tool, history and verifier tests, and tests/cases/: scripted runs with their verdicts
├── ui/              # outputs drawn from their JSON Schema
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier package, one module per tool, and task.py for bisect
```

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

`uv run pytest` runs, without a model and without the network, every tool,
the histories' answer keys, and `tests/cases/`: 22 scripted runs, each its
tool calls, a submission and the verdict it expects (gold runs for every repo,
and wrong, missing, malformed and tampered ones). To rebuild the histories, or
check the bundled ones are what the generator builds:

```bash
uv run python -m plugin.tools_dev.build_histories --check
```

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`;
each run's files are in `bisect/<run>/` in it.
