"""The FrameWebforCS.Headless read check still belongs to the current generator (decision 38).

tests/fixtures/acceptance/frameweb_headless/record.json is what scripts/check_frameweb_headless.py recorded with
FrameWebforCS.Headless (FEMPython). These tests do not run it. For the fixture input they fail (never skip) when a
FrameWeb file is no longer the one that was read: then redo the check with
``uv run --project "." --locked python -X utf8 scripts/check_frameweb_headless.py``. The runs of pre/input.json are
kept as the record of that generation and are not bound here, since that input is edited.
"""

import json
from pathlib import Path

import pytest

from webpier.core.integrity import load_json, sha256
from webpier.export.frameweb.readback import TOLERANCE, expected_counts
from webpier.inputs import parse_input
from webpier.pipeline.generate import export_bytes

ROOT = Path(__file__).parents[2]
RECORD = json.loads((ROOT / "tests/fixtures/acceptance/frameweb_headless/record.json").read_text(encoding="utf-8"))
FIXTURE = "tests/fixtures/inputs/current.json"
RUNS = {run["stage"]: run for run in RECORD["runs"] if run["input"]["path"] == FIXTURE}
REDO = "確認をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/check_frameweb_headless.py"


@pytest.fixture(scope="module")
def documents():
    data = (ROOT / FIXTURE).read_bytes()
    pier = parse_input(load_json(data))
    for run in RUNS.values():
        assert sha256(data) == run["input"]["sha256"], f"受入時の入力から変わっています。{REDO}"
    return {stage: export_bytes(pier, stage, "frameweb") for stage in RUNS}


def test_the_record_is_a_read_check_of_both_files():
    assert RECORD["kind"] == "frameweb_headless_read_check" and RECORD["schema_version"] == 1
    assert set(RUNS) == {"0610", "0620"}
    assert {run["input"]["path"] for run in RECORD["runs"]} == {"pre/input.json", FIXTURE}
    for run in RECORD["runs"]:
        envelope = run["envelope"]
        assert envelope["ok"] is True and envelope["executionStatus"] == "success" and envelope["errors"] == []
        assert envelope["engine"] == "fempython" and envelope["engineeringStatus"] == "not_checked"
        assert {message["code"] for message in envelope["messages"]} == {"EMPTY_LOAD_CASE_SKIPPED"}


@pytest.mark.parametrize("stage", ["0610", "0620"])
def test_the_checked_file_is_what_the_generator_writes_now(documents, stage):
    assert sha256(documents[stage]) == RUNS[stage]["candidate_sha256"], f"{stage} の FrameWeb 入力が変わりました。{REDO}"


@pytest.mark.parametrize("stage", ["0610", "0620"])
def test_everything_written_came_back_except_the_empty_case(documents, stage):
    expected, counts = expected_counts(load_json(documents[stage])), RUNS[stage]["counts"]
    assert counts == {
        "nodes": expected["nodes"], "generated_nodes": counts["generated_nodes"], "members": expected["members"],
        "calculated_cases": expected["load_cases"] - len(expected["empty_load_cases"]),
        "skipped_load_cases": expected["empty_load_cases"],
        "defines": expected["defines"] - len(expected["defines_without_loads"]),
        "combines": expected["combines"], "pickups": expected["pickups"]}
    # current.json: the low-water buoyancy (case 5) is zero; 0620 gets one node where the wind load ends (y 4.7).
    assert (counts["skipped_load_cases"], counts["generated_nodes"]) == (["5"], {"0610": 0, "0620": 1}[stage])


@pytest.mark.parametrize("stage", ["0610", "0620"])
def test_every_calculated_case_balances_the_loads_we_wrote(stage):
    run = RUNS[stage]
    assert len(run["equilibrium"]) == run["counts"]["calculated_cases"]
    for case in run["equilibrium"]:
        for load, reaction in zip(case["applied"], case["reactions"]):
            assert abs(load + reaction) <= TOLERANCE * (1 + abs(load)), case


def test_a_combination_differs_from_the_printed_one_only_by_rounding():
    """Decision 38: 0610 combination 1 is 22585.1473 in FrameWeb against the printed 22585.160 (by hand in
    tests/export/test_frameweb_readback.py); each printed action differs by at most 0.005."""
    combination = RUNS["0610"]["combination"]
    assert combination["printed"] == pytest.approx(22585.16, abs=1e-9)
    assert combination["frameweb"] == pytest.approx(22585.1473, abs=1e-9)
    assert combination["largest_action_difference"] <= 0.005
