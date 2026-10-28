"""The bundled histories: each repo's commits, oldest first, each holding the files it changes."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from contract import Repo

DATA = Path(__file__).parent / "data"


def history_path(repo: Repo) -> Path:
    return DATA / f"{repo.value}.json"


def load_history(repo: Repo) -> dict:
    """``{"repo", "commits": [{"id", "parent", "author", "date", "message", "changes"}]}``, oldest first.

    A commit's ``changes`` maps each file it touches to its new content, or None when it deletes it.
    """
    return json.loads(history_path(repo).read_text())


def history_sha256(repo: Repo) -> str:
    return hashlib.sha256(history_path(repo).read_bytes()).hexdigest()


def check_position(history: dict, position: int) -> None:
    count = len(history["commits"])
    if not 1 <= position <= count:
        raise ValueError(f"position {position} is not in {history['repo']}'s history: positions run 1 to {count}")


def tree_at(history: dict, position: int) -> dict[str, str]:
    """Every file at ``position`` (1 = the oldest commit): the changes of commits 1 to ``position`` applied."""
    check_position(history, position)
    tree: dict[str, str] = {}
    for commit in history["commits"][:position]:
        for path, content in commit["changes"].items():
            if content is None:
                tree.pop(path, None)
            else:
                tree[path] = content
    return tree


def materialize(tree: dict[str, str], folder: Path) -> None:
    """Write ``tree`` into ``folder``, emptied first so no file of another commit is left in it."""
    if folder.exists():
        shutil.rmtree(folder)
    for path, content in tree.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
