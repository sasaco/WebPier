"""The real-FEMPython acceptances of the 0612 / 0622 基礎の照査 still belong to the current generator (decision 54).

tests/fixtures/acceptance/foundation_check/record_<stage>.json and the reaction CSV beside it are what
scripts/accept_foundation_check.py recorded with the real FrameWebforCS.Headless. These tests do not run it. They
fail (never skip) when the FrameWeb file WebPier writes for the fixture input is no longer the one analyzed: then
redo the acceptance with ``uv run --project "." --locked python -X utf8 scripts/accept_foundation_check.py <stage>``.
"""

import json
from pathlib import Path

import pytest

from recorded_input_support import input_sha256s
from webpier.calc import foundation_check as fc
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.integrity import load_json, sha256
from webpier.inputs import parse_input
from webpier.pipeline.fempython import support_reactions
from webpier.pipeline.generate import export_bytes

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
HAND = json.loads((FIXTURES / "example2" / "foundation_check.json").read_text(encoding="utf-8"))
STAGES = {"0612": ("0610", fc.LONGITUDINAL, "8-30", ("vd", "hd", "md")),
          "0622": ("0620", fc.TRANSVERSE, "9-27", ("vd",))}
TOLERANCE = 0.25  # kN, kN m: the sample's hidden digits (longitudinal_notes.md 3, 4)


def redo(stage: str) -> str:
    return f"受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_foundation_check.py {stage}"


@pytest.fixture(scope="module", params=list(STAGES))
def accepted(request):
    stage = request.param
    source, direction, _, _ = STAGES[stage]
    records = FIXTURES / "acceptance" / "foundation_check"
    record = json.loads((records / f"record_{stage}.json").read_text(encoding="utf-8"))
    data = (ROOT / record["input"]["path"]).read_bytes()
    assert record["input"]["sha256"] in input_sha256s(data), f"受入時の入力から変わっています。{redo(stage)}"
    csv = (records / record["reaction"]["file"]).read_bytes()
    assert sha256(csv) == record["reaction"]["sha256"]
    return stage, record, parse_input(load_json(data)), csv, source, direction


def _check(pier, csv, source, direction) -> fc.FoundationCheckResult:
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    frame = (calculate_longitudinal if source == "0610" else calculate_transverse)(pier, foundation, reaction)
    basis = fc.prepare(pier, foundation, frame, direction)
    return fc.check(basis, support_reactions(csv, basis.node))


def test_the_analyzed_frameweb_file_is_what_the_generator_writes_now(accepted):
    stage, record, pier, _, source, _ = accepted
    assert (record["kind"], record["schema_version"], record["stage"], record["accepted"]) == (
        "foundation_check_acceptance", 1, stage, True)
    assert sha256(export_bytes(pier, source, "frameweb")) == record["frameweb_sha256"], (
        f"{source} の FrameWeb 入力が変わりました。{redo(stage)}")


def test_the_actions_read_from_the_real_reactions_are_those_of_example2(accepted):
    """08 8-30: every column within the sample's hidden digits. 09 9-27: the combinations and Vd only (WebPier's 0620
    wind differs from the sample's, decisions 12 and 35)."""
    stage, record, pier, csv, source, direction = accepted
    _, _, page, compared = STAGES[stage]
    sample = HAND["sample_actions"][page]
    for column in _check(pier, csv, source, direction).columns:
        expected = sample[column.key]
        assert column.combination == expected["combination"], column.key
        for name in compared:
            assert abs(getattr(column, name).value - expected[name]) <= TOLERANCE, (column.key, name)
        assert record["columns"][column.key]["ours"] == {"combination": column.combination, "vd": column.vd.value,
                                                         "hd": column.hd.value, "md": column.md.value}


def test_the_real_reactions_give_the_independent_hand_calculation(accepted):
    """The hand calculation took its reactions from these files: with the input made sandy (as pre/input.json, decision
    54), the whole check is the hand calculation's."""
    stage, _, _, csv, source, direction = accepted
    data = load_json((FIXTURES / "inputs" / "current.json").read_bytes())
    data["地盤データ"]["層"][1]["土質区分"] = "砂質土"
    data["地盤データ"]["層"][0]["単位体積重量"]["水中"] = 9.0
    result = _check(parse_input(data), csv, source, direction)
    for column in result.columns:
        hand = HAND["directions"][stage]["columns"][column.key]
        for name in ("vd", "hd", "md", "pd1", "qd", "rhb"):
            assert getattr(column, name).value == hand[name], (column.key, name)
        for name in ("bearing", "vertical", "rotation_ex", "rotation_moment", "horizontal"):
            judged = getattr(column, name)
            assert (judged and judged.value.value) == hand[name], (column.key, name)
