from __future__ import annotations

from pathlib import Path

import pytest
from scripted import load_cases, run_case

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_case_gets_its_expected_verdict(case: dict, tmp_path: Path, pinned: dict) -> None:
    verdict = run_case(case, tmp_path, pinned)
    expect = case["expect"]
    assert verdict["valid"] is expect["valid"], verdict["message"]
    assert verdict["score"] == expect["score"], verdict["message"]
    if expect["check"] is None:
        assert verdict["message"] == "All 9 checks hold."
    else:
        assert verdict["message"].startswith(expect["check"] + ":"), verdict["message"]


def test_the_cases_cover_every_check() -> None:
    from verifier.task import CHECKS

    checked = {case["expect"]["check"] for case in CASES}
    assert set(CHECKS) <= checked | {"budget"}, set(CHECKS) - checked
