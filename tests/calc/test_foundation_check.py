"""0612 / 0622 基礎の照査 (decision 54): the four columns against an independent hand calculation.

The expected values are tests/fixtures/example2/foundation_check.json, calculated by hand from the equations of
decision 54 without the implementation (its notes check that the same equations, given the sample's own inputs,
reproduce Example2 8-30, 8-32, 9-27 and 9-29 but for the documented corrections). The input is current.json with the
supporting layer sandy and the cover's submerged unit weight 9.0, as pre/input.json (decision 54).
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from reaction_support import pier
from webpier.calc import foundation_check as fc
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.printed import Printed

HAND = json.loads((Path(__file__).parents[1] / "fixtures" / "example2" / "foundation_check.json").read_text(
    encoding="utf-8"))
SANDY = {"地盤データ/層/1/土質区分": "砂質土", "地盤データ/層/0/単位体積重量/水中": 9.0}
KEYS = ("long_term", "short_term", "safety_vertical", "safety_moment")
RATIOS = ("bearing", "vertical", "rotation_ex", "rotation_moment", "horizontal")


def prepared(stage: str = "0612", **changes) -> fc.Basis:
    p = pier(**{**SANDY, **changes})
    foundation, reaction = calculate_foundation(p), calculate_reaction(p)
    if stage == "0612":
        return fc.prepare(p, foundation, calculate_longitudinal(p, foundation, reaction), fc.LONGITUDINAL)
    return fc.prepare(p, foundation, calculate_transverse(p, foundation, reaction), fc.TRANSVERSE)


def hand_reactions(stage: str, basis: fc.Basis) -> fc.Reactions:
    """Each column's reaction as both extremes of its pickup and focus (the other extreme never wins)."""
    found = {}
    for key, spec in zip(KEYS, fc.COLUMNS):
        given = HAND["inputs"]["reactions"][stage][key]
        extreme = fc.SupportReaction(given["combination"], float(given["fx"]), float(given["fy"]), float(given["mz"]))
        found[(basis.pickups[key], spec.focus.value)] = (extreme, extreme)
    return found


def reaction(combination: int, fx: float, fy: float, mz: float) -> fc.SupportReaction:
    return fc.SupportReaction(combination, fx, fy, mz)


def uniform(basis: fc.Basis, extreme: fc.SupportReaction) -> fc.Reactions:
    """The same reaction in every column."""
    return {(basis.pickups[key], spec.focus.value): (extreme, extreme) for key, spec in zip(KEYS, fc.COLUMNS)}


@pytest.mark.parametrize("stage", ["0612", "0622"])
def test_the_basis_is_the_hand_calculation(stage):
    basis, hand = prepared(stage), HAND["directions"][stage]
    footing = HAND["inputs"]["footing"][stage]
    assert (basis.b.value, basis.l.value, basis.depth.value) == (footing["B"], footing["L"], 4.7)
    assert (basis.friction_angle.value, basis.gamma_e1.value, basis.n_gamma.value, basis.n_q.value) == (
        42.2, 10.0, 150, 85)
    for level, cover in (("normal", basis.normal), ("high", basis.high)):
        assert (cover.wet_segment.value, cover.submerged_segment.value, cover.unit_weight.value) == (
            hand["gamma_e2"][level]["wet_segment"], hand["gamma_e2"][level]["submerged_segment"],
            hand["gamma_e2"][level]["value"])
    assert basis.long_term_limit == Printed(hand["long_term_limit"], 2, "kN/m2")
    assert (basis.ground.name, basis.soil_type) == ("洪積砂地盤・沖積砂礫地盤", "砂質土")


@pytest.mark.parametrize("stage", ["0612", "0622"])
def test_the_columns_are_the_hand_calculation(stage):
    basis = prepared(stage)
    result = fc.check(basis, hand_reactions(stage, basis))
    assert result.engineering_status == "ok"
    for column in result.columns:
        hand = HAND["directions"][stage]["columns"][column.key]
        for name, expected in hand.items():
            if name == "judgement" or name == "mmd" and column.mmd is None:  # the hand fills Mmd in every column
                continue
            ours = getattr(column, name)
            if name in RATIOS:
                assert (ours and ours.value and ours.value.value) == expected, (column.key, name)
                assert ours is None or ours.ok
            elif isinstance(ours, Printed):
                assert ours.value == expected, (column.key, name)
            else:
                assert ours == expected, (column.key, name)


def test_the_support_node_and_the_pickups_come_from_the_frame_and_its_extraction_groups():
    p = pier(**SANDY)
    foundation, reaction_result = calculate_foundation(p), calculate_reaction(p)
    frame = calculate_longitudinal(p, foundation, reaction_result)
    basis = fc.prepare(p, foundation, frame, fc.LONGITUDINAL)
    assert basis.node == frame.frame.node(NodeRole.FOOTING_BOTTOM).number
    numbers = {extraction.group: extraction.number for extraction in frame.extractions}
    assert basis.pickups == {"long_term": numbers[fc.ExtractionGroup.SUPPORT_LONG_TERM],
                             "short_term": numbers[fc.ExtractionGroup.SUPPORT_SHORT_TERM],
                             "safety_vertical": numbers[fc.ExtractionGroup.STABILITY],
                             "safety_moment": numbers[fc.ExtractionGroup.STABILITY]}


def test_gravel_is_diluvial_gravel_with_the_higher_long_term_limit():
    """owner 2026-10-18: 砂礫 is 洪積砂礫地盤, 500 + γe2・Df = 500 + 12.8 × 4.700 = 560.16."""
    basis = prepared(**{"地盤データ/層/1/土質区分": "砂礫"})
    assert (basis.ground.name, basis.long_term_limit) == ("洪積砂礫地盤", Printed(560.16, 2, "kN/m2"))


@pytest.mark.parametrize("soil", ["粘性土", "砂質土と粘性土の互層"])
def test_a_clayey_supporting_layer_is_an_input_error(soil):
    with pytest.raises(InputError, match=re.escape(f"地盤データ.層[支持層].土質区分: 基礎の照査は砂質土・砂礫だけに対応します（入力 {soil}）")):
        prepared(**{"地盤データ/層/1/土質区分": soil})


def test_the_submerged_unit_weight_of_the_supporting_layer_is_required():
    with pytest.raises(InputError, match=re.escape("地盤データ.層[支持層].単位体積重量.水中: 基礎の照査の γe1 に必要です")):
        prepared(**{"地盤データ/層/1/単位体積重量/水中": None})


def test_the_vertical_extreme_is_the_largest_vd_and_the_moment_one_the_largest_md():
    basis = prepared()
    small, large = reaction(1, 0, -15000, 100), reaction(2, 0, -16000, -900)
    reactions = {(basis.pickups["long_term"], "fy"): (small, large), (basis.pickups["short_term"], "fy"): (large, small),
                 (basis.pickups["safety_vertical"], "fy"): (small, large), (basis.pickups["safety_moment"], "mz"): (
                     small, large)}
    assert [column.combination for column in fc.check(basis, reactions).columns] == [2, 2, 2, 2]
    reactions[(basis.pickups["safety_moment"], "mz")] = (large, reaction(3, 0, -16000, 800))
    assert fc.check(basis, reactions).columns[3].combination == 2


def test_a_missing_pickup_is_a_reaction_error():
    basis = prepared()
    reactions = dict(uniform(basis, reaction(1, 0, -16000, 0)))
    del reactions[(basis.pickups["safety_moment"], "mz")]
    with pytest.raises(fc.ReactionError, match=re.escape("支点の反力のピックアップ 6（mz）がありません")):
        fc.check(basis, reactions)


def test_an_eccentricity_beyond_b_over_6_gives_a_triangle():
    """ex = Md / Vd = 20000 / 16000 = 1.250 > 7/6; x = 3 × (3.5 − 1.25) = 6.750,
    pd1 = 2 × 16000 / (3 × 9 × 2.25) = 526.75, pd2 = 0."""
    basis = prepared()
    column = fc.check(basis, uniform(basis, reaction(1, 0, -16000, 20000))).columns[0]
    assert column.triangular and (column.ex.value, column.width_loaded.value) == (1.25, 6.75)
    assert (column.pd1.value, column.pd2.value) == (526.75, 0)


def test_be_is_l_when_b_effective_is_wider_and_beta_takes_l_over_b():
    """Across the track B′ = 9.000 > L = 7.000: Be = 7.000, βb = 0.5 − 0.2 × 7/9 = 0.344."""
    basis = prepared("0622")
    column = fc.check(basis, uniform(basis, reaction(1, 0, -16000, 0))).columns[0]
    assert (column.b_effective.value, column.b_e.value, column.beta_b.value) == (9.0, 7.0, 0.344)


def test_the_long_term_limit_applies_only_when_it_is_lower():
    basis = replace(prepared(), long_term_limit=Printed(99999.99, 2, "kN/m2"))
    column = fc.check(basis, uniform(basis, reaction(1, 0, -16000, 0))).columns[0]
    assert column.qd == column.qd_unlimited


def test_an_inclination_beyond_phi_makes_i_gamma_zero():
    basis = prepared()
    column = fc.check(basis, uniform(basis, reaction(1, 20000, -16000, 0))).columns[2]
    assert column.delta.value == 51.34 and column.i_gamma.value == 0  # tan⁻¹(20000/16000)


def test_a_vd_beyond_the_capacity_leaves_no_mmd_and_fails():
    basis = prepared()
    result = fc.check(basis, uniform(basis, reaction(1, 0, -3000000, 0)))
    safety = result.columns[2]
    assert safety.mmd.value < 0 and safety.rotation_moment == fc.Judged(None, False)
    assert not safety.vertical.ok and result.engineering_status == "not_ok"


@pytest.mark.parametrize("fy,mz,message", [
    (100, 0, "基礎の照査（長期支持）: フーチング底面の鉛直力 Vd が上向きです（-100.0 kN）"),
    (-16000, 56000, "基礎の照査（長期支持）: 合力の作用位置 ex＝3.5 m がフーチングの外にあり、照査できません"),
])
def test_a_reaction_the_check_cannot_take_is_an_input_error(fy, mz, message):
    basis = prepared()
    with pytest.raises(InputError, match=re.escape(message)):
        fc.check(basis, uniform(basis, reaction(1, 0, fy, mz)))


def test_pick_takes_the_larger_moment_then_the_larger_horizontal_force_among_equal_vertical_forces():
    """Decision 60 (owner 2026-10-19): the two extremes of a pickup with the same fy (the horizontal force in either
    direction: 12.1 使用性) give the row with the larger |mz|, then the larger |fx|; the largest Vd is still the
    smallest fy."""
    plus = fc.SupportReaction(5, 300.0, -19506.36, 3327.12)
    minus = fc.SupportReaction(5, -300.0, -19506.36, -2852.88)
    assert fc.pick({(2, "fy"): (minus, plus)}, 2, fc.Focus.VERTICAL) is plus
    assert fc.pick({(2, "fy"): (plus, minus)}, 2, fc.Focus.VERTICAL) is plus
    wider = fc.SupportReaction(6, -240.0, -18049.95, 1887.75)
    narrower = fc.SupportReaction(6, 100.0, -18049.95, -1887.75)
    assert fc.pick({(3, "fy"): (narrower, wider)}, 3, fc.Focus.VERTICAL) is wider
    heavier = fc.SupportReaction(7, 0.0, -20000.0, 1.0)
    assert fc.pick({(8, "fy"): (heavier, plus)}, 8, fc.Focus.VERTICAL) is heavier
    # FEMPython's fy rows carry one of the two variants of the combination; the other is on the mz (or fx) rows.
    assert fc.pick({(2, "fy"): (minus, minus), (2, "mz"): (plus, minus)}, 2, fc.Focus.VERTICAL) is plus
    assert fc.pick({(2, "fy"): (minus, minus), (2, "fx"): (plus, minus), (2, "mz"): (heavier, minus)}, 2,
                   fc.Focus.VERTICAL) is heavier
