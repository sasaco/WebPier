"""The 地盤変位 of a pile foundation (decision 97, CONTEXT.md 地盤変位).

What the SoilStructure runner is given (the layers above the base, cut at the depths asked for) and how its answer is
read back. The expected rows are hand-cut from the layers; Tg and f(z) are the runner's, so they are made up here.
"""

import json
import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from webpier.calc.ground_displacement import (
    GroundDisplacementError, considered, ground_displacement, region_coefficient, runner_rows, surface_layers)
from webpier.core.errors import InputError
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures" / "inputs"
SEISMIC = json.loads((FIXTURES / "pile_seismic.json").read_text(encoding="utf-8"))
VS = "せん断弾性波速度_Vs"


def pile_input(ground_class="G4地盤", velocities=(170, 120, 140, 180, 330, None)):
    data = deepcopy(SEISMIC)
    data["耐震設計条件"]["地盤区分"] = ground_class
    for layer, velocity in zip(data["地盤データ"]["層"], velocities):
        layer[VS] = velocity
    return data


def test_only_a_pile_foundation_on_g3_to_g5_considers_the_ground_displacement():
    for ground_class, expected in (("G2地盤", False), ("G3地盤", True), ("G4地盤", True), ("G5地盤", True),
                                   ("G0地盤", False), (None, False)):
        assert considered(parse_input(pile_input(ground_class))) is expected
    direct = json.loads((FIXTURES / "current.json").read_text(encoding="utf-8"))
    direct["耐震設計条件"]["地盤区分"] = "G4地盤"
    assert considered(parse_input(direct)) is False


def test_the_surface_layers_are_all_but_the_last_with_their_wet_unit_weight_and_vs():
    layers = surface_layers(parse_input(pile_input()))
    assert [(layer.index, layer.name, layer.top.value, layer.thickness.value, layer.unit_weight.value,
             layer.velocity.value) for layer in layers] == [
        (0, "表層", 0.0, 2.8, 18.0, 170), (1, "第2層", 2.8, 2.6, 18.0, 120), (2, "第3層", 5.4, 5.0, 18.0, 140),
        (3, "第4層", 10.4, 4.0, 15.0, 180), (4, "第5層", 14.4, 6.4, 16.0, 330)]


@pytest.mark.parametrize("index,key,message", [
    (2, VS, f"地盤データ.層[2].{VS}: 地盤変位の算定に必要です（地盤区分 G3〜G5 の杭基礎）"),
    (1, "単位体積重量", "地盤データ.層[1].単位体積重量.湿潤: 地盤変位の算定に必要です（地盤区分 G3〜G5 の杭基礎）"),
])
def test_a_blank_vs_or_unit_weight_above_the_base_is_an_input_error(index, key, message):
    data = pile_input()
    if key == VS:
        data["地盤データ"]["層"][index][VS] = None
    else:
        data["地盤データ"]["層"][index]["単位体積重量"]["湿潤"] = None
    with pytest.raises(InputError, match=re.escape(message)):
        surface_layers(parse_input(data))


def test_the_last_layer_may_leave_vs_blank_it_is_below_the_base():
    assert len(surface_layers(parse_input(pile_input(velocities=(170, 120, 140, 180, 330, None))))) == 5


def test_the_region_coefficient_is_aggrese_s():
    data = pile_input()
    for region, expected in (("A地域", "1.0"), ("B地域", "0.85"), ("C地域", "0.7")):
        data["耐震設計条件"]["地域別"] = region
        assert region_coefficient(parse_input(data)) == Decimal(expected)
    data["耐震設計条件"]["地域別"] = None
    with pytest.raises(InputError, match=re.escape("耐震設計条件.地域別: 地盤変位の算定に必要です")):
        region_coefficient(parse_input(data))


def test_the_rows_cut_each_layer_at_the_depths_and_the_first_row_of_a_layer_carries_its_values():
    layers = surface_layers(parse_input(pile_input()))[:2]  # 2.8 m (18, 170) and 2.6 m (18, 120): the base at 5.4 m
    rows = runner_rows(layers, [Decimal("1.0"), Decimal("2.8"), Decimal("3.0"), Decimal("10.0"), Decimal("1.0")])
    assert [(row.layer, row.thickness, row.unit_weight, row.velocity) for row in rows] == [
        ("1", Decimal("1.000"), Decimal("18.0"), Decimal("170")), ("1", Decimal("1.800"), None, None),
        ("2", Decimal("0.200"), Decimal("18.0"), Decimal("120")), ("2", Decimal("2.400"), None, None)]


def test_more_rows_than_soilstructure_takes_is_an_input_error():
    layers = surface_layers(parse_input(pile_input()))
    depths = [Decimal(index) / 4 for index in range(1, 100)]
    with pytest.raises(InputError, match=re.escape("地盤変位の算定の行が") + r".*" + re.escape("SoilStructure は58行まで")):
        runner_rows(layers, depths)


def _points(rows, values):
    depth = Decimal(0)
    points = [{"depthM": 0, "l1DisplacementMm": values[0][0], "l2SpectrumTwoDisplacementMm": values[0][1]}]
    for row, (l1, l2) in zip(rows, values[1:]):
        depth += row.thickness
        points.append({"depthM": float(depth), "l1DisplacementMm": l1, "l2SpectrumTwoDisplacementMm": l2})
    return points


def test_the_answer_gives_tg_the_profile_at_the_layer_tops_and_the_nodes():
    layers = surface_layers(parse_input(pile_input()))[:2]
    rows = runner_rows(layers, [Decimal("1.0"), Decimal("3.0")])
    points = _points(rows, [(17.114, 220.344), (16.9, 218.0), (13.845, 178.316), (12.0, 150.0), (0.0004, 0.0)])
    ground = ground_displacement(layers, Decimal("0.85"), 0.53349999, points, [Decimal("1.0"), Decimal("3.0"),
                                                                              Decimal("7.5")])
    assert ground.period.value == 0.5335 and ground.region_coefficient == Decimal("0.85")
    assert [(p.depth.value, p.l1.value, p.l2.value) for p in ground.profile] == [
        (0.0, 17.11, 220.34), (2.8, 13.85, 178.32), (5.4, 0.0, 0.0)]
    # a node below the base does not move
    assert [(p.depth.value, p.l1.value, p.l2.value) for p in ground.nodes] == [
        (1.0, 16.9, 218.0), (3.0, 12.0, 150.0), (7.5, 0.0, 0.0)]
    assert ground.at(Decimal("3.0")).l2.value == 150.0


def test_an_answer_without_a_point_at_a_depth_asked_for_is_refused():
    layers = surface_layers(parse_input(pile_input()))[:2]
    rows = runner_rows(layers, [])
    points = _points(rows, [(1, 2), (0.5, 1), (0, 0)])
    with pytest.raises(GroundDisplacementError, match=re.escape("深さ 1.0 m の地盤変位がありません")):
        ground_displacement(layers, Decimal(1), 0.5, points, [Decimal("1.0")])
    with pytest.raises(GroundDisplacementError, match="固有周期"):
        ground_displacement(layers, Decimal(1), 0.0, points, [])
