import pytest

from contract import BisectInput, Repo
from plugin import pin_truth


@pytest.fixture(scope="session")
def pinned(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Each repo's answer key, pinned once: it runs every commit's tests."""
    return {repo: pin_truth(BisectInput(repo=repo), tmp_path_factory.mktemp(repo.value)) for repo in Repo}
