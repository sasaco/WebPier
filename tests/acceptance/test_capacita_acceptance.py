"""The real-Capacita acceptance of the 0611 柱の断面照査 still belongs to the current generator (decision 48).

tests/fixtures/acceptance/capacita/record.json is what scripts/accept_capacita_column.py recorded with the real
WebDanforCS.Headless (and the real FEMPython for the PIK). These tests do not run it. They fail (never skip) when the
WDJ WebPier writes for the fixture input is no longer the one Capacita checked: then redo the acceptance with
``uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py``.
"""

import json
from pathlib import Path

import pytest

from webpier.calc.column_check import calculate_column_check
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.core.integrity import load_json, sha256
from webpier.export.capacita import build_wdj, write_wdj
from webpier.inputs import parse_input

ROOT = Path(__file__).parents[2]
RECORD = json.loads((ROOT / "tests/fixtures/acceptance/capacita/record.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((ROOT / "tests/fixtures/example2/column_section_check.json").read_text(encoding="utf-8"))
REDO = "受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_capacita_column.py"


@pytest.fixture(scope="module")
def check():
    data = (ROOT / RECORD["input"]["path"]).read_bytes()
    assert sha256(data) == RECORD["input"]["sha256"], f"受入時の入力から変わっています。{REDO}"
    pier = parse_input(load_json(data))
    reaction = calculate_reaction(pier)
    return calculate_column_check(pier, calculate_longitudinal(pier, calculate_foundation(pier), reaction))


def test_the_checked_wdj_is_what_the_generator_writes_now(check):
    assert sha256(write_wdj(build_wdj(check))) == RECORD["wdj_given_sha256"], f"0611 の WDJ が変わりました。{REDO}"


def test_the_report_has_the_sections_asked_for(check):
    assert [section["id"] for section in RECORD["report"]["sections"]] == list(check.sections)
    assert RECORD["report"]["sections"][-1]["last"] == RECORD["report"]["pages"]


def test_the_check_ratios_are_those_of_example2():
    """08_線路.pdf 8-15 and 8-26; the capacities differ by less than 0.2 % between the sample's WebDan and Capacita."""
    acceptance = SAMPLE["acceptance"]
    values = RECORD["values"]
    assert RECORD["kind"] == "capacita_column_check_acceptance" and RECORD["schema_version"] == 1
    assert values["bending_safety_destruction"]["ratio"] == acceptance["bending_safety_destruction"]["ratio"]
    assert values["bending_restorability"]["ratio"] == acceptance["bending_restorability"]["ratio"]
    for section, key in (("bending_safety_destruction", "Mud_kNm"), ("bending_restorability", "Myd_kNm")):
        printed, sample = float(values[section]["capacity"]), float(acceptance[section][key])
        assert abs(printed - sample) / sample < 0.002, section
