from __future__ import annotations

import pytest

from contract import Repo
from plugin.history import history_path, history_sha256
from plugin.tools_dev.build_histories import SPECS, build, serialize

SPEC = {spec.repo: spec for spec in SPECS}


@pytest.mark.parametrize("repo", list(Repo))
def test_the_bundled_history_is_what_the_generator_builds(repo: Repo) -> None:
    assert history_path(repo).read_text() == serialize(build(SPEC[repo]))


@pytest.mark.parametrize("repo", list(Repo))
def test_the_answer_key_is_the_specs(repo: Repo, pinned: dict) -> None:
    assert pinned[repo].statuses == SPEC[repo].expected
    assert pinned[repo].history_sha256 == history_sha256(repo)


def test_commit_ids_are_unique_across_repos(pinned: dict) -> None:
    ids = [commit for key in pinned.values() for commit in key.ids]
    assert len(set(ids)) == len(ids)
