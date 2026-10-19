"""0800 フーチングの応答値 (decision 60): one direction assembled from the input, 0500, the frame of 0610 / 0620, the
support reactions and the step table — ``prepare`` before the analyses, ``complete`` after them.

The input is current.json made sandy (as pre/input.json) with the sample's footing bars; the reactions are the
sample's columns given as FEMPython returns them (fy downward, decision 54) and the step table the stand-in's rows.
Expected values: the sample transcription footing.json (q1, qd1/qd2/X1/X2, self weight, buoyancy) and the hand
calculation footing_hand.json (the trapezoid rows with the corrected q2, and the seismic column of this input);
nothing is computed by the code under test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from footing_support import COMBINATIONS, DIRECTIONS, NON_SEISMIC, STEPS, completed, footing_pier, prepared, reactions
from webpier.calc import foundation_check as fc
from webpier.calc import footing
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.printed import Printed

FIXTURES = Path(__file__).parents[1] / "fixtures" / "example2"
SAMPLE = json.loads((FIXTURES / "footing.json").read_text(encoding="utf-8"))
HAND = json.loads((FIXTURES / "footing_hand.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_basis_reads_the_frame_the_footing_and_the_bars(direction):
    basis, frame_result = prepared(direction)
    geo = SAMPLE["directions"][direction]
    numbers = {extraction.group: extraction.number for extraction in frame_result.extractions}
    assert basis.direction == DIRECTIONS[direction].name
    assert (basis.check.b.value, basis.check.l.value, basis.check.depth.value) == (geo["B"], geo["L"], 4.7)
    assert basis.node == frame_result.frame.node(NodeRole.FOOTING_BOTTOM).number
    assert basis.pickups == {key: numbers[spec.group] for key, spec in zip(NON_SEISMIC, footing.COLUMNS)}
    assert (basis.width.column.value, basis.width.left.value, basis.width.right.value, basis.width.be.value,
            basis.width.full.value) == (geo["column_across"], geo["overhang_across"], geo["overhang_across"],
                                        geo["be"], geo["full_width"])
    assert basis.width.d.value == {"0800_longitudinal": 2.6, "0800_transverse": 2.573}[direction]
    assert basis.rebar.main.cover.value == {"0800_longitudinal": 100, "0800_transverse": 127}[direction]
    assert [(side.name, side.length.value, side.cover_depth.value) for side in basis.sides] == [
        ("起点側", geo["L1"], 2.0), ("終点側", geo["L1"], 2.0)]
    for side in basis.sides:
        assert (side.weight.w.value, side.weight.m.value) == (geo["self_weight"]["W"], geo["self_weight"]["M"])
        assert (side.water.high.w.value, side.water.normal.w.value, side.water.low.w.value) == (
            geo["buoyancy"]["high"]["W"], geo["buoyancy"]["normal"]["W"], geo["buoyancy"]["low"]["W"])


@pytest.mark.parametrize("key", NON_SEISMIC)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_each_non_seismic_column_is_its_pickup_and_the_hand_calculation(direction, key):
    result = completed(direction)
    given, hand = SAMPLE["directions"][direction]["columns"][key], HAND["directions"][direction]["columns"][key]
    column = result.column(key)
    assert (column.key, column.limit, column.detail) == (key, given_limit(key), given_detail(key))
    assert (column.source.pickup, column.source.combination, column.source.case_name, column.source.step) == (
        result.basis.pickups[key], COMBINATIONS[key], None, None)
    assert (column.vd.value, column.hd.value, column.md.value) == (given["Vd"], given["Hd"], given["Md"])
    assert (column.capacity.ex.value, column.capacity.b_effective.value, column.alpha_b.value) == (
        given["ex"], given["B_eff"], given["alpha_b"])
    assert (column.distribution.case, column.distribution.qd1.value, column.distribution.qd2.value,
            column.distribution.x1.value) == (1, given["qd1"], given["qd2"], given["X1"])
    assert column.chosen == 0 and [side.side for side in column.sides] == ["起点側", "終点側"]
    assert (column.sides[0].segments, column.sides[0].forces) == (column.sides[1].segments, column.sides[1].forces)
    (segment,) = column.sides[0].segments
    assert (segment.q1.value, segment.q2.value, segment.w.value, segment.x.value, segment.m.value) == (
        hand["reaction"]["q1"], hand["reaction"]["q2"], hand["reaction"]["W"], hand["reaction"]["x"],
        hand["reaction"]["M"])
    forces = column.forces
    assert (forces.m_full.value, forces.m_per_m.value, forces.md.value, forces.v_full.value, forces.v_per_m.value,
            forces.vd.value, forces.la.value) == (hand["M_full"], hand["M_per_m"], hand["Md_design"],
                                                  hand["V_full"], hand["V_per_m"], hand["Vd_design"], hand["La"])


def given_limit(key: str) -> str:
    return "安全性" if key.startswith("safety") else "使用性"


def given_detail(key: str) -> str:
    return {"safety_moment": "Ｍd最大", "safety_shear": "Ｖd最大", "short_term": "短期", "long_term": "長期"}[key]


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_seismic_column_is_the_rvd_step_with_this_inputs_capacity(direction):
    result = completed(direction)
    hand = HAND["directions"][direction]["seismic_own_input"]
    column = result.column("seismic")
    assert (column.limit, column.detail) == ("地震時", "")
    assert (column.source.pickup, column.source.case_index, column.source.case_name, column.source.step,
            column.source.rvd.value) == (None, 0, "Case1", 3, 16655.87)
    assert (column.vd.value, column.hd.value, column.md.value) == (hand["Vd"], hand["Hd"], hand["Md"])
    capacity = column.capacity
    assert (capacity.ex.value, capacity.b_effective.value, capacity.area_effective.value, capacity.delta.value,
            capacity.gamma_e2.value, capacity.i_gamma.value, capacity.i_q.value, capacity.beta_b.value,
            capacity.term_gamma.value, capacity.term_q.value, capacity.qvd.value, capacity.qd_unlimited.value,
            capacity.mmd.value, column.alpha_b.value) == (
        hand["ex"], hand["B_eff"], hand["A_eff"], hand["delta"], hand["gamma_e2"], hand["Ir"], hand["Iq"],
        hand["beta_b"], hand["term_gamma"], hand["term_q"], hand["qvd"], hand["qd"], hand["Mmd"], hand["alpha_b"])
    dist = column.distribution
    assert (dist.case, dist.apex.value, dist.qd1.value, dist.qd2.value, dist.x1.value, dist.x2.value) == (
        hand["case"], hand["apex"], hand["qd1"], hand["qd2"], hand["X1"], hand["X2"])
    assert column.chosen == 0
    side = column.sides[0]
    assert [(s.q1.value, s.q2.value, s.length.value, s.w.value, s.x.value, s.m.value) for s in side.segments] == [
        (s["q1"], s["q2"], s["length"], s["W"], s["x"], s["M"]) for s in hand["segments"]]
    assert (side.w.value, side.m.value) == (hand["W"], hand["M"])
    assert (side.forces.md.value, side.forces.vd.value, side.forces.la.value) == (hand["Md_design"],
                                                                                  hand["Vd_design"], hand["La"])


def test_the_columns_are_in_the_order_of_the_sample():
    result = completed("0800_longitudinal")
    assert [column.key for column in result.columns] == [spec.key for spec in footing.COLUMNS]


@pytest.mark.parametrize("direction,path", [("0800_longitudinal", "下部構造/寸法/側面/B9"),
                                            ("0800_transverse", "下部構造/寸法/正面/W9")])
def test_the_longer_overhang_is_taken_when_the_sides_differ(direction, path):
    # The 終点側 overhang made 0.500 longer: a larger Md on that side in every column.
    result = completed(direction, **{path: SAMPLE["directions"][direction]["L1"] + 0.5})
    for column in result.columns:
        assert column.chosen == 1
        assert column.sides[1].forces.md.value > column.sides[0].forces.md.value
        assert column.forces == column.sides[1].forces
    assert [side.length.value for side in result.basis.sides] == [SAMPLE["directions"][direction]["L1"],
                                                                 SAMPLE["directions"][direction]["L1"] + 0.5]


def test_unequal_cover_depths_are_the_input_error_of_the_embedment():
    # The sides carry df1 and df2, but 0612's basis (Df, γ2 of a flat cover) already refuses unequal ones.
    with pytest.raises(InputError, match="起点側_df1（2.0 m）と終点側_df2（1.5 m）が異なり"):
        prepared("0800_longitudinal", **{"下部構造/土かぶり/終点側_df2": 1.5})
    basis, _ = prepared("0800_longitudinal")
    assert [side.cover_depth.value for side in basis.sides] == [2.0, 2.0]


def test_a_missing_pickup_is_the_reaction_error_of_0612():
    basis, _ = prepared("0800_longitudinal")
    given = reactions("0800_longitudinal", basis)
    del given[(basis.pickups["long_term"], "fy")]
    with pytest.raises(fc.ReactionError, match="ピックアップ"):
        footing.complete(basis, given, STEPS)


def test_a_step_table_that_never_reaches_rvd_is_a_steps_error():
    basis, _ = prepared("0800_longitudinal")
    with pytest.raises(footing.StepsError, match="Rvd到達ステップがありません"):
        footing.complete(basis, reactions("0800_longitudinal", basis), STEPS[:2])


def test_an_upward_vd_in_a_column_is_an_input_error_naming_the_column():
    basis, _ = prepared("0800_longitudinal")
    given = reactions("0800_longitudinal", basis)
    pickup = basis.pickups["short_term"]
    extreme = fc.SupportReaction(13, 0.0, 10.0, 0.0)
    given[(pickup, "fy")] = (extreme, extreme)
    with pytest.raises(InputError, match="フーチングの応答値（使用性 短期）: フーチング底面の鉛直力 Vd が上向きです"):
        footing.complete(basis, given, STEPS)


def test_blank_footing_bars_stop_prepare_before_any_analysis():
    with pytest.raises(InputError, match="鉄筋.フーチング.main_rows"):
        prepared("0800_longitudinal", **{"鉄筋/フーチング/main_rows/1/diameter_mm": None})


def test_the_result_of_both_directions():
    longitudinal, transverse = completed("0800_longitudinal"), completed("0800_transverse")
    result = footing.FootingResult(longitudinal, transverse)
    assert (result.longitudinal.basis.direction, result.transverse.basis.direction) == ("線路", "直角")
    assert isinstance(result.longitudinal.column("seismic").forces.la, Printed)


def test_both_directions_are_prepared_before_the_analyses_and_completed_after_them():
    """0800 as the pipeline drives it (decision 60): ``calculate_footing`` reads the input, 0500 and the frames of 0610
    and 0620 before any runner; ``complete_footing`` finishes both directions with their reactions and step tables."""
    pier = footing_pier()
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    frames = calculate_longitudinal(pier, foundation, reaction), calculate_transverse(pier, foundation, reaction)
    bases = footing.calculate_footing(pier, foundation, *frames)
    assert (bases.longitudinal.direction, bases.transverse.direction) == ("線路", "直角")
    assert bases.longitudinal == prepared("0800_longitudinal")[0]
    result = footing.complete_footing(bases, (reactions("0800_longitudinal", bases.longitudinal), STEPS),
                                      (reactions("0800_transverse", bases.transverse), STEPS))
    assert result == footing.FootingResult(completed("0800_longitudinal"), completed("0800_transverse"))
