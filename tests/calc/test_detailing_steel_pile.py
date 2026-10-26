"""杭の構造細目 of a 鋼管ソイルセメント杭 (decision 99): 0400's (1) 鋼管杭, (2) 杭とフーチングの結合部, (3) ソイルセメント.

The expected values are transcribed from the sample Example橋脚4 II-18〜29 (D 800, t 18, 腐食代 1, Dsc 1000, D38 − 16 本
SD390 at 75 mm, 中詰め f'ck 27 and Dmax 25, フーチング f'ck 27), on pile.json switched to that pile, except where the
hand calculation written below differs from the sample:

- ld01: k1 is printed 1.15 and used so (ADR-0003): 1.15 × (0.7 × 390／20.8 ＋ 11) × 38 = 1054.3 → 1054 (the sample's 1053
  is from k1 unrounded), ld01 − 10φ = 674 (673);
- lc by the H26 formula: l'd = 0.6 × 390／(4 × 1.9) × 38 = 1170, lh = (3.0 ＋ 1)φ = 152, 100 ＋ 1170 ＋ 152 ＋ 100 = 1522 →
  1550 (the sample's table gives 1550);
- the ずれ止め: two steps until the seismic check (the sample has 3), the lowest 1550 − (200 ＋ 250) = 1100 from the bottom
  of the filling against lz0 = max(200, 250) = 250 (the sample: 750 and D／4 = 200).
"""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import webpier.calc.detailing as detailing_module
from webpier.calc.detailing import calculate_detailing
from webpier.calc.detailing.steel_pile import steel_pile_detailing
from webpier.core.errors import InputError
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures" / "inputs"
PILE = json.loads((FIXTURES / "pile.json").read_text(encoding="utf-8"))
EXAMPLE4 = json.loads((FIXTURES / "example4.json").read_text(encoding="utf-8"))


def sample(**steel):
    data = deepcopy(PILE)
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["杭基礎"]["鋼管ソイルセメント杭"] = deepcopy(EXAMPLE4["杭基礎"]["鋼管ソイルセメント杭"])
    data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["粗骨材の最大寸法"] = 25.0
    data["杭基礎"]["鋼管ソイルセメント杭"].update(steel)
    data["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 27.0
    return data


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
