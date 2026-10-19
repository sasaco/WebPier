"""The geometry of each cantilever (decision 59; Example2 13-23, 13-24): which bearings it carries, their arms, the
torsion arm, Σxi² of each girder and the self weight. Expected values are the transcription cantilever.json and
hand calculations from the input."""

from __future__ import annotations

import re

import pytest

from cantilever_support import SAMPLE, D, pier, q, reaction_of, value
from webpier.calc.cantilever import Side, calculate_cantilever
from webpier.calc.cantilever.geometry import GIRDER_SIDES, geometry, numbered
from webpier.calc.moving_load import Girder
from webpier.core.errors import InputError


@pytest.fixture(scope="module")
def current():
    pier_input = pier()
    return pier_input, reaction_of(pier_input)


def test_the_bearings_are_numbered_by_position_with_their_torsional_constant(current):
    pier_input, reaction = current
    girders = numbered(reaction.dead)
    origin, end = girders[Girder.ORIGIN], girders[Girder.END]
    assert [item.position.value for item in origin.bearings] == [-3.8, -1.5, 1.5, 3.8]
    assert [item.number for item in origin.bearings] == [1, 2, 3, 4]
    assert [item.label for item in origin.bearings] == ["Ｇ1桁", "Ｇ2桁", "Ｇ3桁", "Ｇ4桁"]
    assert origin.sum_squares.value == SAMPLE["torques"]["sum_squares"]["origin"]  # 2 × (1.5² + 3.8²) = 33.3800
    assert origin.sum_squares.digits == 4 and origin.side == "起点側"
    assert [item.position.value for item in end.bearings] == [-2.95, 2.95]
    assert end.sum_squares.value == SAMPLE["torques"]["sum_squares"]["end"]  # 2 × 2.95² = 17.4050
    assert end.side == "終点側" and GIRDER_SIDES[Girder.END] == "終点側"
    # the loads of a numbered bearing are the input's
    assert origin.bearings[0].loads.bearing.d1.value == 1530.0 and origin.bearings[0].loads.slot == 0


def test_the_left_cantilever_carries_g1_of_both_girders(current):
    pier_input, reaction = current
    left = geometry(pier_input, reaction.dead, Side.LEFT)
    expected = SAMPLE["geometry"]
    assert left.side is Side.LEFT and left.overhang.value == expected["overhang"]
    assert left.half_column.value == expected["half_column"]
    assert left.torsion_arm.value == expected["torsion_arm_y"]  # (2.000 + 0.700) / 2
    assert [(item.girder, item.bearing.number) for item in left.bearings] == [(Girder.ORIGIN, 1), (Girder.END, 1)]
    origin, end = left.bearings
    assert (origin.x.value, origin.e.value) == (expected["origin_g1"]["x"], expected["origin_g1"]["e"])
    assert (end.x.value, end.e.value) == (expected["end_g1"]["x"], expected["end_g1"]["e"])  # 0.700, not 0.645
    assert origin.x.digits == 3 and origin.label == "起点側 Ｇ1桁" and end.label == "終点側 Ｇ1桁"


def test_the_right_cantilever_mirrors_the_left_for_the_symmetric_input(current):
    pier_input, reaction = current
    left, right = (geometry(pier_input, reaction.dead, side) for side in Side)
    assert right.side is Side.RIGHT and right.overhang.value == pier_input.substructure.w[5].value
    assert [(item.girder, item.bearing.number) for item in right.bearings] == [(Girder.ORIGIN, 4), (Girder.END, 2)]
    assert [(item.x.value, item.e.value) for item in right.bearings] == [(item.x.value, item.e.value)
                                                                        for item in left.bearings]
    assert right.self_weight == left.self_weight
    assert Side.LEFT.sign == -1 and Side.RIGHT.sign == 1


def test_the_self_weight_of_the_cantilever(current):
    pier_input, reaction = current
    weight = geometry(pier_input, reaction.dead, Side.LEFT).self_weight
    expected = SAMPLE["self_weight"]
    assert weight.unit_weight.value == 24.5
    assert (weight.rectangle.force.value, weight.rectangle.arm.value, weight.rectangle.moment.value) == (
        expected["rectangle"]["force"], expected["rectangle"]["arm"], expected["rectangle"]["moment"])
    assert (weight.haunch.force.value, weight.haunch.arm.value, weight.haunch.moment.value) == (
        expected["haunch"]["force"], expected["haunch"]["arm"], expected["haunch"]["moment"])
    assert (weight.force.value, weight.moment.value) == (expected["total"]["force"], expected["total"]["moment"])
    # by hand: 24.5 × 2.70 × 2.00 × 2.25 and 24.5 × 2.70 × 0.70 × 2.25 / 2, the arms W/2 and W/3
    assert value(weight.rectangle.force) == q(D(24.5) * D(2.7) * D(2.0) * D(2.25), 2)
    assert value(weight.haunch.force) == q(D(24.5) * D(2.7) * D(0.7) * D(2.25) / 2, 2)
    assert value(weight.haunch.arm) == q(D(2.25) / 3, 3)
    assert value(weight.moment) == q(D(334.89) + D(39.07), 2)
    assert (weight.rectangle.width, weight.rectangle.depth, weight.rectangle.length) == (
        pier_input.substructure.b[1], pier_input.substructure.h[2], pier_input.substructure.w[4])


def test_a_bearing_on_the_column_is_not_on_a_cantilever(current):
    pier_input, reaction = current
    assert all(abs(item.position.value) > 2.25 for side in Side
               for item in (bearing.bearing for bearing in geometry(pier_input, reaction.dead, side).bearings))
    # G2 and G3 at ±1.5 are inside the column (|x| ≤ W6/2) and belong to neither side
    carried = {(side, bearing.girder, bearing.bearing.number) for side in Side
               for bearing in geometry(pier_input, reaction.dead, side).bearings}
    assert (Side.LEFT, Girder.ORIGIN, 2) not in carried and (Side.RIGHT, Girder.ORIGIN, 3) not in carried


def test_a_bearing_at_the_column_face_stays_on_the_column():
    pier_input = pier(**{"上部工反力/起点側/B支点/0/支承位置": -2.25})
    left = geometry(pier_input, reaction_of(pier_input).dead, Side.LEFT)
    assert [(item.girder, item.bearing.number) for item in left.bearings] == [(Girder.END, 1)]


def test_a_bearing_beyond_the_overhang_is_an_input_error():
    pier_input = pier(**{"上部工反力/終点側/C支点/1/支承位置": 4.6})
    with pytest.raises(InputError, match=re.escape("上部工反力.終点側.C支点[1].支承位置: はりの張出し（W6/2 + W5 = 4.5 m）"
                                                   "の外にあります（4.6 m）")):
        geometry(pier_input, reaction_of(pier_input).dead, Side.RIGHT)
    pier_input = pier(**{"上部工反力/起点側/B支点/0/支承位置": -4.501})
    with pytest.raises(InputError, match=re.escape("上部工反力.起点側.B支点[0].支承位置") + ".*W4"):
        calculate_cantilever(pier_input, reaction_of(pier_input))


def test_without_a_cantilever_bearing_the_check_is_an_input_error():
    changes = {f"上部工反力/起点側/B支点/{index}/支承位置": position for index, position in enumerate((-2.0, -1.5, 1.5, 2.0))}
    changes |= {"上部工反力/終点側/C支点/0/支承位置": -2.2, "上部工反力/終点側/C支点/1/支承位置": 2.2}
    pier_input = pier(**changes)
    with pytest.raises(InputError, match=re.escape("上部工反力: はりの張出し（|支承位置| > W6/2）に支承がないため")):
        calculate_cantilever(pier_input, reaction_of(pier_input))


def test_a_one_sided_input_has_one_cantilever():
    pier_input = pier(**{"上部工反力/起点側/B支点/3/支承位置": 2.0, "上部工反力/終点側/C支点/1/支承位置": 2.0})
    basis = calculate_cantilever(pier_input, reaction_of(pier_input))
    assert list(basis.sides) == [Side.LEFT]
    assert [(item.girder, item.bearing.number) for item in basis.sides[Side.LEFT].bearings] == [(Girder.ORIGIN, 1),
                                                                                                 (Girder.END, 1)]


def test_a_blank_beam_aggregate_size_is_an_input_error():
    pier_input = pier(**{"鉄筋/梁/aggregate_max_mm": None})
    with pytest.raises(InputError, match=re.escape("鉄筋.梁.aggregate_max_mm: 値が必要です")):
        calculate_cantilever(pier_input, reaction_of(pier_input))
