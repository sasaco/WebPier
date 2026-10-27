"""The real-Capacita acceptances of the 0611 / 0621 柱の断面照査 still belong to the current generator (decision 48).

tests/fixtures/acceptance/capacita/record.json (0611) and record_0621.json are what scripts/accept_capacita_column.py
recorded with the real WebDanforCS.Headless (and the real FEMPython for the PIK). These tests do not run it. They fail
(never skip) when the WDJ WebPier writes for the fixture input is no longer the one Capacita checked: then redo the
acceptance with ``uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py <stage>``.
"""

import json
from pathlib import Path

import pytest

from column_capacity_by_hand import mud
from recorded_input_support import input_sha256s
from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.integrity import load_json, sha256
from webpier.export.capacita import build_wdj, write_wdj
from webpier.inputs import parse_input
from webpier.pipeline.generate import export_bytes
from reactions_by_hand import reference_frameweb

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
STAGES = {"0611": ("record.json", "column_section_check.json"), "0621": ("record_0621.json", "column_section_check_09.json")}


def redo(stage: str) -> str:
    return f"受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_capacita_column.py {stage}"


def record(stage: str) -> dict:
    return json.loads((FIXTURES / "acceptance" / "capacita" / STAGES[stage][0]).read_text(encoding="utf-8"))


def sample(stage: str) -> dict:
    return json.loads((FIXTURES / "example2" / STAGES[stage][1]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=list(STAGES))
def accepted(request):
    stage = request.param
    recorded = record(stage)
    data = (ROOT / recorded["input"]["path"]).read_bytes()
    assert recorded["input"]["sha256"] in input_sha256s(data), f"受入時の入力から変わっています。{redo(stage)}"
    pier = parse_input(load_json(data))
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    check = (calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE)
             if stage == "0621" else
             calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL))
    return stage, recorded, check


def test_the_checked_wdj_is_what_the_generator_writes_now(accepted):
    """At the point the recorded PIK had (the transcription's: 6 along the track, 7 across it)."""
    stage, recorded, check = accepted
    assert recorded["point_index"] == sample(stage)["check_point"]["index"]
    assert sha256(write_wdj(build_wdj(check, recorded["point_index"]))) == recorded["wdj_given_sha256"], (
        f"{stage} の WDJ が変わりました。{redo(stage)}")


def test_the_report_has_the_sections_asked_for_but_those_capacita_skipped(accepted):
    stage, recorded, check = accepted
    report = recorded["report"]
    assert sorted(report["skipped"]) == sorted(sample(stage)["acceptance"].get("skipped_by_capacita", []))
    assert [section["id"] for section in report["sections"]] == [
        section for section in check.sections if section not in report["skipped"]]
    assert report["sections"][-1]["last"] == report["pages"]


def test_the_values_are_those_of_example2(accepted):
    """Mud of both agrees within 0.2 % with the hand calculation for the sample's N'd (column_capacity_by_hand: decision
    105 counts the side bars, the H16 sample does not). 08_線路.pdf 8-26: the check ratio of 使用性（損傷）and Myd within
    0.2 % (the sample's WebDan and Capacita). 09_直角.pdf: neither (WebPier's 0620 wind differs, decisions 12 and 35, and
    decision 103 changes the bars)."""
    stage, recorded, _ = accepted
    acceptance, values = sample(stage)["acceptance"], recorded["values"]
    assert (recorded["kind"], recorded["schema_version"], recorded["stage"]) == (
        "capacita_column_check_acceptance", 2, stage)
    assert abs(float(values["bending_safety_destruction"]["capacity"]) - mud(stage)) / mud(stage) < 0.002
    if stage == "0611":
        section = "bending_restorability"
        assert values[section]["ratio"] == acceptance[section]["ratio"]
        printed, expected = float(values[section]["capacity"]), float(acceptance[section]["Myd_kNm"])
        assert abs(printed - expected) / expected < 0.002


def test_capacita_checked_the_pik_of_the_current_frameweb_file_too(accepted):
    """Decision 77: the values above are for the reference file (the impact of the girder coefficients, which is what
    Example2 has). The PIK of the file the generator writes now was given to Capacita as well, which checked the same
    sections and skipped the same ones; its values are Capacita's and are not compared."""
    stage, recorded, _ = accepted
    data = (ROOT / recorded["input"]["path"]).read_bytes()
    pier = parse_input(load_json(data))
    source = "0620" if stage == "0621" else "0610"
    current = recorded["current"]
    assert sha256(export_bytes(pier, source, "frameweb")) == current["frameweb_sha256"], (
        f"{stage} の FrameWeb 入力が変わりました。{redo(stage)}")
    assert sha256(reference_frameweb(pier, source)) == current["reference_frameweb_sha256"], redo(stage)
    assert sorted(current["skipped"]) == sorted(recorded["report"]["skipped"])
    assert set(current["values"]) == set(recorded["values"])
