"""杭の構造細目 of a 鋼管ソイルセメント杭 (decision 99): 0400's (1) 鋼管杭, (2) 杭とフーチングの結合部, (3) ソイルセメント.

The expected values are transcribed from the sample Example橋脚4 II-18〜29 (D 800, t 18, 腐食代 1, Dsc 1000, D38 − 16 本
SD390 at 75 mm, 中詰め f'ck 27 and Dmax 25, フーチング f'ck 27), on pile.json switched to that pile, except where the
hand calculation written below differs from the sample:

- ld01: k1 is printed 1.15 and used so (ADR-0003): 1.15 × (0.7 × 390／20.8 ＋ 11) × 38 = 1054.3 → 1054 (the sample's 1053
  is from k1 unrounded), ld01 − 10φ = 674 (673);
- lc by the H26 formula: l'd = 0.6 × 390／(4 × 1.9) × 38 = 1170, lh = (3.0 ＋ 1)φ = 152, 100 ＋ 1170 ＋ 152 ＋ 100 = 1522 →
  1550 (the sample's table gives 1550);
- the ずれ止め: two steps from the input alone (the sample has 3), the lowest 1550 − (200 ＋ 250) = 1100 from the bottom
  of the filling against lz0 = max(200, 250) = 250 (the sample: 750 and D／4 = 200).

The ずれ止めの杭頭反力に対する検討 (decision 123, the sample V-179〜181, tests/fixtures/example4/joint_ribs.json) by hand,
on the same pile (D 800, t0 18, t 17, t' 16, lz 250, 中詰め and フーチング f'ck 27, lc 1550, D／4 200, lz0 250):

- τd = (3.5 ＋ 190 × 27 × 16／250 × 17／800)／1.3 = 10.4768／1.3 = 8.059 → 8.06 (≦ 15);
- Aa = π／4 × (800² − 764²) = π／4 × 56304 = 44221.06 → 44221; Rd = 1 × 27 × 44221／1.3 = 918436.2 → 918436;
- the bond capacity π(D − 2t)・Ld・τd = π × 766 × 250n × 8.06, not printed: 9698033.7 (n = 2), 14547050.5 (n = 3),
  24245084.2 (n = 5);
- the most steps: lc − {D／4 ＋ (n − 1)lz} ≧ lz0 → n ≦ (1550 − 250 − 200)／250 ＋ 1 = 5.4 → 5.
"""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import webpier.calc.detailing as detailing_module
from webpier.calc.detailing import calculate_detailing, with_joint_forces as with_result_forces
from webpier.calc.detailing.steel_pile import (JointAxial, bond_strength, rib_bond, steel_pile_detailing,
                                               with_joint_forces)
from webpier.core.printed import Printed
from webpier.core.errors import InputError
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT

FIXTURES = Path(__file__).parents[1] / "fixtures" / "inputs"
PILE = json.loads((FIXTURES / "pile.json").read_text(encoding="utf-8"))
EXAMPLE4 = json.loads(EXAMPLE4_INPUT.read_text(encoding="utf-8"))


def sample(**steel):
    data = deepcopy(PILE)
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["杭基礎"]["鋼管ソイルセメント杭"] = deepcopy(EXAMPLE4["杭基礎"]["鋼管ソイルセメント杭"])
    data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["粗骨材の最大寸法"] = 25.0
    data["杭基礎"]["鋼管ソイルセメント杭"].update(steel)
    data["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 27.0
    # its 0400 uses the seismic checks of both directions (decision 123)
    data["outputs"] = {key: key in STEEL_ITEMS for key in data["outputs"]}
    return data


STEEL_ITEMS = ("detailing", "ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis",
               "transverse_seismic", "transverse_nonlinear_analysis")


def detailing(data=None):
    return steel_pile_detailing(parse_input(data if data is not None else sample()))


def joint(data, **items):
    data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"].update(items)
    return data


def bars(data, **items):
    data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["軸方向鉄筋"].update(items)
    return data


def test_the_pipe_is_the_sample_1_2_1():
    pipe = detailing().pipe
    assert (pipe.diameter.value, pipe.soil_cement.value, pipe.diameter_ok) == (800, 1000, True)
    assert (pipe.made.value.value, pipe.made.ratio.value, pipe.made.percent.value, pipe.made.ok) == (18, 0.0225, 2.25, True)
    effective = pipe.effective
    assert (effective.value.value, effective.ratio.value, effective.percent.value, effective.ok) == (17, 0.0213, 2.13, True)
    tip = pipe.tip
    assert (tip.row, tip.steps, tip.first.value, tip.pitch.value, tip.length.value) == (800, 4, 300, 250, 1050)
    assert (tip.penetration.value, tip.margin.value, tip.embedment.value, tip.ok, pipe.ok) == (1200, 500, 1000, True, True)


def test_the_joint_is_the_sample_1_2_2():
    found = detailing().joint
    assert (found.grade_ok, found.size_ok, found.cover.value, found.cover_ok) == (True, True, 38, True)
    assert (found.pitch.value, found.clear.value, found.aggregate_limit.value, found.bar_limit.value) == (128, 90, 33.3, 57.0)
    assert (found.clear_ok, found.rib_gap.value, found.rib_gap_ok) == (True, 22, True)
    assert (found.bar_area.value, found.pc.value, found.pc_ok) == (18240.0, 3.63, True)
    item = found.anchorage
    assert (item.fsyd.value, item.fcd.value, item.spacing.value, item.spacing_limit.value, item.k1.value) == (
        390, 20.8, 128, 380, 1.15)
    assert (item.ld01.value, item.hook.value, item.reduced.value, item.least.value, item.ld0.value) == (
        1054, 380, 674, 760, 760)
    assert (item.ineffective.value, item.sum.value, item.l1.value) == (190, 950, 950)
    fill = found.filling
    assert (fill.fbod.value, fill.anchorage.value, fill.required.value, fill.hook.value) == (1.9, 1170, 1270, 152)
    assert (fill.least.value, fill.sum.value, fill.length.value) == (1200, 1522, 1550)


def test_the_hoops_and_the_ribs_are_decided_by_the_rules():
    found = detailing().joint
    hoops = found.footing_hoops
    assert (hoops.diameter.value, hoops.upper.value, hoops.lower_pitch.value, hoops.upper_pitch.value) == (16, 22, 125, 200)
    assert hoops.positions == tuple(Decimal(value) for value in (75, 200, 325, 525, 725, 925))  # 図1.2.3
    inner = found.pipe_hoops
    assert (inner.diameter.value, inner.range.value, inner.divisions, inner.pitch.value, inner.count, inner.ok) == (
        10, 1198, 4, 250, 5, True)
    assert inner.positions == tuple(Decimal(value) for value in (100, 350, 600, 850, 1100))
    ribs = found.ribs
    assert (ribs.grade, ribs.thickness.value, ribs.width.value, ribs.width_least.value, ribs.spacing.value) == (
        "SS400", 16, 32, 32, 250)
    assert (ribs.quarter.value, ribs.bottom_least.value, ribs.steps, ribs.bottom.value, ribs.ok) == (200, 250, 2, 1100, True)


def test_the_soil_cement_is_the_sample_1_2_3():
    soil = detailing().soil_cement
    assert [(name, value.value) for name, value in soil.strengths] == [
        ("杭一般部（砂質土）", 1000), ("杭一般部（粘性土）", 750), ("杭先端部（砂質土）", 15000)]
    assert soil.ok and detailing().ok


def test_0400_of_a_steel_pile_has_its_detailing_and_its_status(monkeypatch):
    # pile.json's beam does not satisfy its own detailing: a beam that does leaves the status to the pile
    monkeypatch.setattr(detailing_module, "beam_detailing", lambda pier: SimpleNamespace(ok=True))
    result = calculate_detailing(parse_input(sample()))
    assert result.pile is None and result.steel_pile is not None and result.engineering_status == "ok"
    thin = calculate_detailing(parse_input(sample(鋼管厚=9.0)))
    assert thin.engineering_status == "not_ok"


def test_a_thin_pipe_has_no_flat_bar_for_its_ribs():
    found = detailing(sample(鋼管厚=9.0))  # effective 8: below 1.25 % of 800 and below the 9 of 表1.10-1
    assert (found.pipe.effective.ratio.value, found.pipe.effective.ok, found.pipe.made.ok) == (0.01, False, True)
    ribs = found.joint.ribs
    assert (ribs.thickness, ribs.width, ribs.spacing, ribs.bottom, ribs.ok) == (None, None, None, None, False)
    assert (found.joint.rib_gap, found.joint.rib_gap_ok, found.joint.ok, found.ok) == (None, False, False, False)


def test_a_pipe_of_19_mm_takes_the_19_flat_bar_and_a_pipe_of_25_mm_stops_at_20():
    assert detailing(sample(鋼管厚=20.0)).joint.ribs.thickness.value == 19  # effective 19
    ribs = detailing(sample(鋼管厚=25.0)).joint.ribs  # effective 24, at most 20 → 19
    assert (ribs.thickness.value, ribs.width.value, ribs.spacing.value) == (19, 38, 300)


def test_a_diameter_between_rows_takes_the_larger_and_one_beyond_the_table_has_none():
    tip = detailing(sample(鋼管外径=0.85, ソイルセメント径=1.05)).pipe.tip
    assert (tip.row, tip.steps, tip.length.value) == (900, 5, 1300)
    big = detailing(sample(鋼管外径=1.3, ソイルセメント径=1.5)).pipe
    assert (big.diameter_ok, big.tip.row, big.tip.length, big.tip.ok, big.ok) == (False, None, None, False, False)


def test_rules_outside_the_handbook_are_not_ok():
    found = detailing(bars(sample(), 材質="SD295", 径=41, 本数=8))
    assert (found.joint.grade_ok, found.joint.size_ok, found.joint.ok) == (False, False, False)
    small = detailing(sample(ソイルセメント径=0.95))  # Dsc − Dsp = 150
    assert (small.soil_cement.ok, small.ok) == (False, False)
    crowded = detailing(bars(sample(), 本数=24))  # π × 650／24 = 85, clear 47 < 57.0
    assert (crowded.joint.pitch.value, crowded.joint.clear.value, crowded.joint.clear_ok) == (85, 47, False)
    many = detailing(bars(sample(), 本数=40))  # pc = 45600／502654.8 = 9.07 %
    assert (many.joint.pc.value, many.joint.pc_ok) == (9.07, False)
    few = detailing(bars(sample(), 径=19, 本数=8))  # pc = 2292／502654.8 = 0.46 %
    assert (few.joint.pc.value, few.joint.pc_ok) == (0.46, False)


def test_smaller_anchor_bars_take_the_smaller_hoops_and_pitches():
    found = detailing(bars(sample(), 径=25, 本数=24)).joint  # 解説表1.10-1: D13; 解説図1.10-5: 100・150
    hoops = found.footing_hoops
    assert (hoops.diameter.value, hoops.lower_pitch.value, hoops.upper_pitch.value) == (13, 100, 150)
    assert detailing(bars(sample(), 径=16, 本数=24)).joint.footing_hoops.diameter.value == 10
    wide = detailing(sample(鋼管外径=1.1, ソイルセメント径=1.3)).joint.footing_hoops
    assert wide.upper is None  # the D22 bound is for D ≦ 1000


def test_a_weaker_footing_keeps_the_hook_reduced_length():
    data = sample()
    data["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 21.0
    item = detailing(data).joint.anchorage
    # f'cd 21／1.3 = 16.2; 1.15 × (0.7 × 390／16.2 ＋ 11) × 38 = 1.15 × 27.852 × 38 = 1217.1 → 1217; − 380 = 837 ≧ 760
    assert (item.fcd.value, item.ld01.value, item.reduced.value, item.ld0.value) == (16.2, 1217, 837, 837)
    assert (item.sum.value, item.l1.value) == (1027, 1050)  # 837 ＋ 190, rounded up to 50 mm


def test_wide_bars_use_10_phi_as_their_spacing():
    item = detailing(bars(sample(), 径=19, 本数=12)).joint.anchorage  # π × 650／12 = 170 < 190 = 10φ
    assert (item.spacing.value, item.spacing_limit.value) == (170, 190)
    sparse = detailing(bars(sample(), 径=19, 本数=8)).joint.anchorage  # π × 650／8 = 255 > 190
    assert sparse.spacing.value == 190


@pytest.mark.parametrize(("change", "message"), [
    (lambda data: joint(data, 粗骨材の最大寸法=None), "結合部.粗骨材の最大寸法: 杭の構造細目に必要です"),
    (lambda data: joint(data, **{"中詰めコンクリート_f'ck": None}), "結合部.中詰めコンクリート_f'ck: 杭の構造細目に必要です"),
    (lambda data: bars(data, 径=None), "結合部.軸方向鉄筋.径: 杭の構造細目に必要です"),
    (lambda data: bars(data, 重心位置=400.0), "結合部.軸方向鉄筋.重心位置: 鋼管外径に対して大きすぎます"),
    (lambda data: joint(data, **{"中詰めコンクリート_f'ck": 26.0}), "f'ck 26 の付着強度がありません（中詰めコンクリート長"),
    (lambda data: bars(data, 材質="SD490"), "結合部.軸方向鉄筋.材質: SD490 の半円形フックの曲げ内半径"),
])
def test_a_blank_or_impossible_joint_is_an_input_error(change, message):
    with pytest.raises(InputError, match=message.replace("(", r"\(").replace(")", r"\)")):
        detailing(change(sample()))


def test_an_input_without_the_aggregate_key_reads_it_blank():
    data = sample()
    del data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["粗骨材の最大寸法"]
    assert parse_input(data).piles.steel_soil_cement.joint.fill_aggregate_max is None
    with pytest.raises(InputError, match="粗骨材の最大寸法: 杭の構造細目に必要です"):
        detailing(data)


def kN(value, direction="線路直角方向"):
    return JointAxial(Printed(value, 2, "kN"), direction)


def ratios(bond):
    return (None if bond.tension_ratio is None else bond.tension_ratio.value,
            None if bond.compression_ratio is None else bond.compression_ratio.value)


def test_the_bond_check_at_the_sample_s_three_steps_is_v_181():
    """The sample's Nd 5695.00 kN and Np 6796.00 kN at n = 3 (Ld = 750): 5695000／14547050.5 = 0.391 → 0.39 and
    6796000／(14547050.5 ＋ 918436) = 6796000／15465486.5 = 0.439 → 0.44 (V-181)."""
    bond = rib_bond(detailing(), 3, kN(5695.00), kN(6796.00, "線路方向"))
    assert (bond.fill_fck.value, bond.thickness.value, bond.spacing.value, bond.effective.value, bond.diameter.value) == (
        27.0, 16, 250, 17, 800)
    assert (bond.tau.value, bond.footing_fck.value, bond.made.value, bond.inner.value) == (8.06, 27.0, 18, 764)
    assert (bond.area.value, bond.bearing.value, bond.steps, bond.length.value, bond.most) == (44221, 918436, 3, 750, 5)
    assert (bond.tension_n.value, bond.compression_n.value) == (5695000, 6796000)
    assert (bond.tension.direction, bond.compression.direction) == ("線路直角方向", "線路方向")
    assert ratios(bond) == (0.39, 0.44) and bond.ok


def test_the_sample_s_forces_take_two_steps():
    """n = 2 (Ld = 500): 5695000／9698033.7 = 0.587 → 0.59, 6796000／(9698033.7 ＋ 918436) = 0.640 → 0.64; both ≦ 1.00,
    so the least steps are 2 (the sample chose 3: decision 123 (3))."""
    found = with_joint_forces(detailing(), kN(5695.00), kN(6796.00))
    bond = found.joint.bond
    assert (bond.steps, bond.length.value, ratios(bond), bond.ok) == (2, 500, (0.59, 0.64), True)
    assert (found.joint.ribs.steps, found.joint.ribs.bottom.value, found.joint.ribs.ok, found.ok) == (2, 1100, True, True)


def test_webpier_s_forces_take_two_steps():
    """Nd 6576.14 kN, Np 6910.83 kN at n = 2: 6576140／9698033.7 = 0.678 → 0.68, 6910830／10616469.7 = 0.651 → 0.65."""
    bond = with_joint_forces(detailing(), kN(6576.14), kN(6910.83)).joint.bond
    assert (bond.steps, ratios(bond), bond.ok) == (2, (0.68, 0.65), True)


def test_a_tension_two_steps_cannot_carry_takes_three():
    """Nd 10000.00 kN: n = 2 gives 10000000／9698033.7 = 1.031 → 1.03 > 1.00, n = 3 gives 10000000／14547050.5 = 0.687 →
    0.69; the lowest step 1550 − (200 ＋ 2 × 250) = 850 ≧ 250."""
    found = with_joint_forces(detailing(), kN(10000.00), kN(6796.00))
    bond, ribs = found.joint.bond, found.joint.ribs
    assert (bond.steps, bond.length.value, bond.tension_ratio.value, bond.ok) == (3, 750, 0.69, True)
    assert (ribs.steps, ribs.bottom.value, ribs.ok, found.ok) == (3, 850, True, True)
    assert rib_bond(detailing(), 2, kN(10000.00), None).tension_ratio.value == 1.03


def test_a_ratio_rounded_to_1_00_is_satisfied():
    """At n = 2 a ratio rounds to 1.00 up to 1.005 × capacity. Tension: 1.005 × 9698033.7 = 9746523.9 N, so Nd 9746.52 kN
    gives 9746520／9698033.7 = 1.0049996 → 1.00 (2 steps) and 9746.53 kN gives 1.0050006 → 1.01 (3 steps).
    Compression: 1.005 × (9698033.7 ＋ 918436) = 10669552.0 N, so Np 10669.55 kN gives 10669550／10616469.7 = 1.0049998 →
    1.00 and 10669.56 kN gives 1.0050008 → 1.01."""
    edge = with_joint_forces(detailing(), kN(9746.52), None).joint.bond
    assert (edge.steps, ratios(edge), edge.ok) == (2, (1.00, None), True)
    assert rib_bond(detailing(), 2, kN(9746.53), None).tension_ratio.value == 1.01
    assert with_joint_forces(detailing(), kN(9746.53), None).joint.bond.steps == 3
    tight = with_joint_forces(detailing(), None, kN(10669.55)).joint.bond
    assert (tight.steps, ratios(tight), tight.ok) == (2, (None, 1.00), True)
    assert rib_bond(detailing(), 2, None, kN(10669.56)).compression_ratio.value == 1.01
    assert with_joint_forces(detailing(), None, kN(10669.56)).joint.bond.steps == 3


def test_forces_the_most_steps_cannot_carry_are_not_ok():
    """Nd 30000.00 kN at the most steps n = 5 (Ld 1250): 30000000／24245084.2 = 1.237 → 1.24 > 1.00; the lowest step is
    1550 − (200 ＋ 4 × 250) = 350 ≧ 250."""
    found = with_joint_forces(detailing(), kN(30000.00), kN(6796.00))
    bond, ribs = found.joint.bond, found.joint.ribs
    assert (bond.steps, bond.most, bond.length.value, bond.tension_ratio.value, bond.tension_ok) == (
        5, 5, 1250, 1.24, False)
    assert (bond.compression_ok, bond.ok, ribs.steps, ribs.bottom.value, ribs.ok) == (True, False, 5, 350, True)
    assert (found.joint.ok, found.ok) == (False, False)


def test_a_check_without_tension_or_compression_is_left_out():
    """Nd None: Np 6796.00 kN alone, 0.64 at n = 2. Np None: Nd 10000.00 kN alone takes 3 (1.03 at 2, 0.69 at 3).
    Neither: 2 steps, both checks left out."""
    pushed = with_joint_forces(detailing(), None, kN(6796.00)).joint.bond
    assert (pushed.tension, pushed.tension_n, pushed.steps, ratios(pushed), pushed.ok) == (
        None, None, 2, (None, 0.64), True)
    pulled = with_joint_forces(detailing(), kN(10000.00), None).joint.bond
    assert (pulled.compression, pulled.compression_n, pulled.steps, ratios(pulled)) == (None, None, 3, (0.69, None))
    neither = with_joint_forces(detailing(), None, None).joint.bond
    assert (neither.steps, ratios(neither), neither.ok) == (2, (None, None), True)


def test_the_input_alone_keeps_two_steps_and_no_check():
    found = detailing()
    assert (found.joint.ribs.steps, found.joint.ribs.bottom.value, found.joint.bond) == (2, 1100, None)


def test_a_pipe_without_a_flat_bar_has_no_check():
    thin = detailing(sample(鋼管厚=9.0))
    assert with_joint_forces(thin, kN(5695.00), kN(6796.00)) is thin


def test_a_short_filling_keeps_two_steps_whose_position_is_not_ok():
    """A filling of 600 mm (replaced in the result): n ≦ (600 − 250 − 200)／250 ＋ 1 = 1.6 → 1 < 2, so 2 steps whose
    lowest is 600 − (200 ＋ 250) = 150 < 250, and the check is at 2 steps: 0.59・0.64 as above."""
    found = detailing()
    short = replace(found, joint=replace(found.joint, filling=replace(found.joint.filling, length=Printed(600, 0, "mm"))))
    checked = with_joint_forces(short, kN(5695.00), kN(6796.00))
    bond, ribs = checked.joint.bond, checked.joint.ribs
    assert (bond.most, bond.steps, ratios(bond), bond.ok) == (1, 2, (0.59, 0.64), True)
    assert (ribs.steps, ribs.bottom.value, ribs.ok, checked.ok) == (2, 150, False, False)


def test_the_bond_strength_stops_at_15():
    """D 800, t0 25 (t 24, t' 19, lz 300), 中詰め f'ck 50: (3.5 ＋ 190 × 50 × 19／300 × 24／800)／1.3 = 21.55／1.3 = 16.58
    → 15 (解(2.4-19) ≦ 15); the sample's 27 with t' 16, lz 250, t 17 stays 8.06."""
    thick = detailing(joint(sample(鋼管厚=25.0), **{"中詰めコンクリート_f'ck": 50.0}))
    assert rib_bond(thick, 2, None, None).tau.value == 15.0

    def mm(value):
        return Printed(value, 0, "mm")

    assert bond_strength(Printed(27.0, 1, "N/mm2"), mm(16), mm(250), mm(17), mm(800)).value == 8.06


@pytest.mark.parametrize("value", [0.0, -5695.0])
def test_an_axial_force_is_positive(value):
    with pytest.raises(ValueError, match="正の値が必要です"):
        kN(value)


def test_0400_takes_the_forces_and_its_status_again(monkeypatch):
    monkeypatch.setattr(detailing_module, "beam_detailing", lambda pier: SimpleNamespace(ok=True))
    result = calculate_detailing(parse_input(sample()))
    carried = with_result_forces(result, kN(10000.00), kN(6796.00))
    assert (carried.steel_pile.joint.ribs.steps, carried.steel_pile.joint.bond.steps) == (3, 3)
    assert (carried.engineering_status, carried.column, carried.footing_parts) == (
        "ok", result.column, result.footing_parts)
    failed = with_result_forces(result, kN(30000.00), None)
    assert (failed.steel_pile.joint.ribs.steps, failed.engineering_status) == (5, "not_ok")


EXAMPLE4_RIBS = json.loads((Path(__file__).parents[1] / "fixtures" / "example4" / "joint_ribs.json").read_text(
    encoding="utf-8"))
EXAMPLE4_RIBS_N2 = (0.59, 0.64)  # joint_ribs_notes.md: the sample's operands at n = 2


def test_the_bond_check_is_the_transcription_of_v_181():
    """The independent transcription of V-179〜181 (joint_ribs.json): τd, Aa, Rd, Ld and both ratios at the sample's n = 3
    with its Nd 5695000 N and Np 6796000 N; and at n = 2 the ratios of its notes."""
    sample_bond, bearing, check = (EXAMPLE4_RIBS[key] for key in ("bond_strength", "bearing_capacity", "check"))
    nd, np_ = (kN(check[key] / 1000) for key in ("Nd_N", "Np_N"))
    bond = rib_bond(detailing(), check["n"], nd, np_)
    assert (bond.tau.value, bond.area.value, bond.bearing.value, bond.length.value) == (
        sample_bond["tau_d_N_mm2"], bearing["Aa_mm2"], bearing["Rd_N"], check["Ld_mm"])
    assert (bond.tension_n.value, bond.compression_n.value) == (check["Nd_N"], check["Np_N"])
    assert ratios(bond) == (check["tension_check"]["ratio"], check["compression_check"]["ratio"])
    assert ratios(rib_bond(detailing(), 2, nd, np_)) == EXAMPLE4_RIBS_N2


def head(nd_largest, nd_smallest, point="ITAN", focus="N"):
    from webpier.calc.pile_body import PointForces, SectionForce
    return PointForces(focus, point, 0.0, SectionForce(0.0, 0.0, nd_largest, 1), SectionForce(0.0, 0.0, nd_smallest, 2))


def test_the_joint_forces_are_the_largest_of_one_pile_at_the_heads():
    """Of the bundles at the heads: tension 900／3 = 300 and 700／2 = 350 (線路方向), 1050／3 = 350 (線路直角方向, equal, so
    線路方向's); compression 9000／3 = 3000, 7000／2 = 3500 and 11000／3 = 3666.666… → 3666.67 (線路直角方向). A tip (JTAN), a
    focus M, a tension of compression and a compression of tension are not read."""
    from webpier.calc.detailing.steel_pile import joint_axial
    longitudinal = [([head(900.0, -9000.0), head(5000.0, -50000.0, "JTAN"), head(8000.0, -80000.0, focus="M")], 3),
                    ([head(700.0, -7000.0)], 2)]
    transverse = [([head(1050.0, -11000.0)], 3), ([head(-10.0, 20.0)], 1)]
    directions = [("線路方向", longitudinal), ("線路直角方向", transverse)]
    assert joint_axial(directions, True) == kN(350.00, "線路方向")
    assert joint_axial(directions, False) == kN(3666.67, "線路直角方向")


def test_no_tension_or_compression_is_none():
    """Bundles all in compression have no Nd, all in tension no Np; one that rounds to 0.00 kN per pile is none."""
    from webpier.calc.detailing.steel_pile import joint_axial
    pushed = [("線路方向", [([head(-100.0, -900.0)], 3)])]
    pulled = [("線路方向", [([head(900.0, 100.0)], 3)])]
    assert (joint_axial(pushed, True), joint_axial(pulled, False)) == (None, None)
    assert joint_axial([("線路方向", [([head(0.004, -0.004)], 1)])], True) is None
    assert joint_axial([], False) is None
