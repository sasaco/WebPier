"""The real-FEMPython acceptances of the 0612 / 0622 基礎の照査 still belong to the current generator (decision 54).

tests/fixtures/acceptance/foundation_check/record_<stage>.json and the reaction CSV beside it are what
scripts/accept_foundation_check.py recorded with the real FrameWebforCS.Headless. These tests do not run it. They
fail (never skip) when the FrameWeb file WebPier writes for the fixture input is no longer the one analyzed: then
redo the acceptance with ``uv run --project "." --locked python -X utf8 scripts/accept_foundation_check.py <stage>``.

Two files were analyzed (decision 77): the one the generator writes now, whose real reactions are held to the sum of the
loads of each combination, and the reference with the impact of the girder coefficients, whose real reactions are those
of Example2 (which has no reduction on the pier body) and give the independent hand calculation where WebPier reads the
combination Example2 reads: every column of 0622, the long-term column of 0612. Decision 120 made the 0612 short-term
column the edge-stress check and the safety columns every safety check, at low and high water (Example2 is H16,
classification 3): those reference reactions are held to the sum of the loads instead.
"""

import json
from pathlib import Path

import pytest

from reactions_by_hand import by_hand, reference_frameweb, reference_numbers, reference_result
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
# stage: (the load stage, the direction, the sample page, the actions compared, the columns compared with the sample;
# the others are held to the sum of the loads, decision 120)
STAGES = {"0612": ("0610", fc.LONGITUDINAL, "8-30", ("vd", "hd", "md"), ("long_term",)),
          "0622": ("0620", fc.TRANSVERSE, "9-27", ("vd",), tuple(spec.key for spec in fc.COLUMNS))}
TOLERANCE = 0.25  # kN, kN m: the sample's hidden digits (longitudinal_notes.md 3, 4)
HAND_TOLERANCE = 0.05  # kN, kN m: the real run's unrounded factors against the printed ones


def redo(stage: str) -> str:
    return f"受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_foundation_check.py {stage}"


@pytest.fixture(scope="module", params=list(STAGES))
def accepted(request):
    stage = request.param
    source, direction, _, _, _ = STAGES[stage]
    records = FIXTURES / "acceptance" / "foundation_check"
    record = json.loads((records / f"record_{stage}.json").read_text(encoding="utf-8"))
    data = (ROOT / record["input"]["path"]).read_bytes()
    assert record["input"]["sha256"] in input_sha256s(data), f"受入時の入力から変わっています。{redo(stage)}"
    csv = (records / record["reference"]["reaction"]["file"]).read_bytes()
    assert sha256(csv) == record["reference"]["reaction"]["sha256"]
    assert sha256((records / record["reaction"]["file"]).read_bytes()) == record["reaction"]["sha256"]
    return stage, record, parse_input(load_json(data)), csv, source, direction


def _check(pier, csv, source, direction) -> fc.FoundationCheckResult:
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    frame = (calculate_longitudinal if source == "0610" else calculate_transverse)(pier, foundation, reaction)
    basis = fc.prepare(pier, foundation, frame, direction)
    return fc.check(basis, support_reactions(csv, basis.node))


def test_the_analyzed_frameweb_file_is_what_the_generator_writes_now(accepted):
    stage, record, pier, _, source, _ = accepted
    assert (record["kind"], record["schema_version"], record["stage"], record["accepted"]) == (
        "foundation_check_acceptance", 2, stage, True)
    assert sha256(export_bytes(pier, source, "frameweb")) == record["frameweb_sha256"], (
        f"{source} の FrameWeb 入力が変わりました。{redo(stage)}")
    assert sha256(reference_frameweb(pier, source)) == record["reference"]["frameweb_sha256"], (
        f"{source} の参照の FrameWeb 入力が変わりました。{redo(stage)}")


def test_the_real_reactions_of_the_current_file_are_the_sum_of_the_loads(accepted):
    """The frame is statically determinate: the reaction of the combination a column reads is the sum of the loads
    WebPier gives it (Vd within the unrounded factors; 0610 also Fx and Mz; 0620 tells no alternative from the row)."""
    stage, record, pier, _, source, direction = accepted
    records = FIXTURES / "acceptance" / "foundation_check"
    csv = (records / record["reaction"]["file"]).read_bytes()
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    frame = (calculate_longitudinal if source == "0610" else calculate_transverse)(pier, foundation, reaction)
    basis = fc.prepare(pier, foundation, frame, direction)
    reactions = support_reactions(csv, basis.node)
    for spec in fc.COLUMNS:
        row = fc.pick(reactions, basis.pickups[spec.key], spec.focus)
        hand = by_hand(frame, row.combination, row.fx, basis.node)
        assert abs(-row.fy - hand.vd) <= HAND_TOLERANCE, (stage, spec.key, "vd")
        if hand.fx is not None:
            assert abs(row.fx - hand.fx) <= HAND_TOLERANCE and abs(row.mz - hand.mz) <= HAND_TOLERANCE, (
                stage, spec.key)
        assert record["columns"][spec.key]["real"]["combination"] == row.combination


def test_the_actions_read_from_the_real_reactions_are_those_of_example2(accepted):
    """08 8-30: the long-term column only, within the sample's hidden digits, its combination WebPier's 長期支持 whatever
    the sample's number; the other columns read other combinations since decision 120 and are the sum of the loads of
    the combination WebPier picked. 09 9-27: the combinations and Vd only (WebPier's 0620 wind differs from the
    sample's, decisions 12 and 35)."""
    stage, record, pier, csv, source, direction = accepted
    _, _, page, compared, with_sample = STAGES[stage]
    sample = HAND["sample_actions"][page]
    reference = reference_result(pier, source)
    numbers = reference_numbers(reference) if source == "0610" else None
    foundation = calculate_foundation(pier)
    basis = fc.prepare(pier, foundation, reference, direction)
    reactions = support_reactions(csv, basis.node)
    assert record["reference"]["compared_columns"] == list(with_sample)
    for spec, column in zip(fc.COLUMNS, fc.check(basis, reactions).columns, strict=True):
        recorded = record["reference"]["columns"][column.key]
        assert {key: recorded["ours"][key] for key in ("combination", "vd", "hd", "md")} == {
            "combination": column.combination, "vd": column.vd.value, "hd": column.hd.value, "md": column.md.value}
        if column.key not in with_sample:
            assert recorded["compared_with"] == "by_hand"
            row = fc.pick(reactions, basis.pickups[spec.key], spec.focus)
            hand = by_hand(reference, numbers[row.combination], row.fx, basis.node)
            assert abs(-row.fy - hand.vd) <= HAND_TOLERANCE, (stage, column.key, "vd")
            assert abs(row.fx - hand.fx) <= HAND_TOLERANCE and abs(row.mz - hand.mz) <= HAND_TOLERANCE, (
                stage, column.key)
            continue
        assert recorded["compared_with"] == "example2"
        expected = sample[column.key]
        if numbers is None:  # 0622: numbered as Example2 (decision 106)
            assert column.combination == expected["combination"], column.key
        else:  # 0612: by the check (decision 120 renumbered the combinations)
            group = next(extraction for extraction in reference.extractions if extraction.group is spec.group)
            assert numbers[column.combination] in group.combinations, column.key
            assert recorded["ours"]["webpier_combination"] == numbers[column.combination]
        for name in compared:
            assert abs(getattr(column, name).value - expected[name]) <= TOLERANCE, (column.key, name)


def test_the_real_reactions_give_the_independent_hand_calculation(accepted):
    """The hand calculation took its reactions from Example2's files: with the input made sandy (as pre/input.json,
    decision 54), the whole check of each column that still reads Example2's combination is the hand calculation's.
    The 0612 short-term and safety columns read other combinations since decision 120 (classification 3); their
    actions are held to the sum of the loads above, and the hand calculation of the same equations is still that of
    the 0612 long-term column and every 0622 column."""
    stage, _, _, csv, source, direction = accepted
    *_, with_sample = STAGES[stage]
    data = load_json((FIXTURES / "inputs" / "current.json").read_bytes())
    data["地盤データ"]["層"][1]["土質区分"] = "砂質土"
    data["地盤データ"]["層"][0]["単位体積重量"]["水中"] = 9.0
    result = _check(parse_input(data), csv, source, direction)
    checked = [column for column in result.columns if column.key in with_sample]
    assert checked
    for column in checked:
        hand = HAND["directions"][stage]["columns"][column.key]
        for name in ("vd", "hd", "md", "pd1", "qd", "rhb"):
            assert getattr(column, name).value == hand[name], (column.key, name)
        for name in ("bearing", "vertical", "rotation_ex", "rotation_moment", "horizontal"):
            judged = getattr(column, name)
            assert (judged and judged.value.value) == hand[name], (column.key, name)
