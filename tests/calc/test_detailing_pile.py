"""杭の構造細目 of a 場所打ち杭 (decision 98): 0400's (2), (3) and the 杭頭定着長, and (1) of 0711 / 0721.

The expected values of (1)〜(3) are transcribed from the sample .claude/docs/Example橋脚/output/0440_照査の前提.pdf (2.4,
2 pages: D 1200, f'ck 21, D32 − 16 本 SD390, ds 156, Pvmax 7403.05 kN, 1/β 3.55 m, D19 ctc125 and D16 ctc125); the input
is pile_seismic.json changed to the sample's pile. The 杭頭定着長 has no sample: it is the hand calculation written below
(RC標準 2.3.7.3 as the sheet 基本定着長D16 of 照査の前提.xlsm prints it).
"""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from webpier.calc.detailing.pile import minimum_bars, pile_detailing, pile_head_reaction
from webpier.core.errors import InputError
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
PILE = json.loads((FIXTURES / "inputs" / "pile_seismic.json").read_text(encoding="utf-8"))
BOTH = (("線路方向", 3.55), ("線路直角方向", 3.55))


def sample(**lower):
    data = deepcopy(PILE)
    data["杭基礎"]["場所打ち杭"].update({"杭径": 1.2, "f'ck": 21.0})
    data["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 24.0
    bars = data["鉄筋"]["杭"]
    bars["materials"]["main"] = "SD390"
    bars["pure_cover_mm"] = 121.0  # ds = 121 + 19 + 32／2 = 156 (the sample)
    bars["main_bars"] = {"diameter_mm": 32, "count": 16}
    bars["hoops"]["zone_2d"] = {"diameter_mm": 19, "sets": 1, "pitch_mm": 125.0}
    bars["hoops"]["lower"] = [{"length_m": 5.0, "diameter_mm": 16, "sets": 1, "pitch_mm": 125.0}]
    for key, value in lower.items():
        bars[key] = value
    return data


def detailing(data=None, betas=BOTH):
    return pile_detailing(parse_input(data if data is not None else sample()), betas)


def test_the_bending_minimum_is_the_sample_2():
    found = detailing()
    assert (found.section.bar_area.value, found.section.radius.value, found.section.centre.value) == (12707.2, 600, 156)
    bending = found.bending
    assert (bending.tension_area.value, bending.width.value, bending.depth.value) == (3176.8, 848.5, 1044.0)
    assert (bending.ratio.value, bending.minimum.value, bending.ok) == (0.359, 0.2, True)


def test_the_hoops_are_the_sample_3():
    hoops = detailing().hoops
    [span] = hoops.spans
    assert (span.directions, span.inverse_beta.value, span.ratio.value, span.tough) == (
        ("線路方向", "線路直角方向"), 3.55, 1.85, True)
    assert (hoops.head.unit_area.value, hoops.head.legs.value, hoops.head.width.value, hoops.head.pitch.value) == (
        286.5, 2, 1200, 125.0)
    assert (hoops.head.ratio.value, hoops.head.minimum.value, hoops.head.ok) == (0.382, 0.35, True)
    [lower] = hoops.lower
    assert (lower.name, lower.unit_area.value, lower.ratio.value, lower.minimum.value, lower.ok) == (
        "第1区間", 198.6, 0.265, 0.2, True)
    assert hoops.ok and detailing().ok


def test_a_shear_span_ratio_above_2_5_asks_0_30_percent_and_each_direction_prints_its_own():
    hoops = detailing(betas=(("線路方向", 5.0), ("線路直角方向", 4.9))).hoops
    assert [(span.directions, span.ratio.value, span.tough) for span in hoops.spans] == [
        (("線路方向",), 2.6, False), (("線路直角方向",), 2.55, False)]  # 5.0／1.92 = 2.604, 4.9／1.92 = 2.552
    assert (hoops.tough, hoops.head.minimum.value) == (False, 0.3)
    one = detailing(betas=(("線路方向", 5.0), ("線路直角方向", 4.8))).hoops  # 4.8／1.92 = 2.50: 2.5 or less
    assert (one.tough, one.head.minimum.value) == (True, 0.35)


def test_too_few_hoops_are_not_ok():
    data = sample()
    data["鉄筋"]["杭"]["hoops"]["zone_2d"]["pitch_mm"] = 150.0  # 286.5 × 2／(1200 × 150) = 0.318 %
    data["鉄筋"]["杭"]["hoops"]["lower"][0]["pitch_mm"] = 200.0  # 198.6 × 2／(1200 × 200) = 0.166 %
    hoops = detailing(data).hoops
    assert (hoops.head.ratio.value, hoops.head.ok, hoops.lower[0].ratio.value, hoops.lower[0].ok) == (
        0.318, False, 0.166, False)
    assert not hoops.ok


def test_too_few_bars_for_bending_are_not_ok():
    data = sample(main_bars={"diameter_mm": 19, "count": 12})  # 286.5 × 12／4 = 859.5; d = 1200 − 149.5 = 1050.5
    found = detailing(data)
    assert (found.bending.tension_area.value, found.bending.depth.value) == (859.5, 1050.5)
    assert (found.bending.ratio.value, found.bending.ok) == (0.096, False)  # 100 × 859.5／(848.5 × 1050.5)
    assert not found.ok


def test_the_zones_beyond_the_2d_zone_are_checked_above_the_cut_off_only():
    data = sample()
    bars = data["鉄筋"]["杭"]
    bars["hoops"]["lower"] = [{"length_m": 3.0, "diameter_mm": 16, "sets": 1, "pitch_mm": 125.0},
                              {"length_m": 4.0, "diameter_mm": 13, "sets": 1, "pitch_mm": 150.0},
                              {"length_m": 5.0, "diameter_mm": 13, "sets": 1, "pitch_mm": 300.0}]
    assert [zone.name for zone in detailing(data).hoops.lower] == ["第1区間", "第2区間", "第3区間"]  # no cut-off
    bars["cutoff"]["main_bars"] = {"diameter_mm": 29, "count": 16}
    bars["cutoff"]["cutoff_length_mm"] = 5400.0  # the 2D zone ends at 2400, 第1区間 at 5400: 第2区間 starts at the cut-off
    assert [zone.name for zone in detailing(data).hoops.lower] == ["第1区間"]
    bars["cutoff"]["cutoff_length_mm"] = 5401.0
    assert [zone.name for zone in detailing(data).hoops.lower] == ["第1区間", "第2区間"]
    bars["cutoff"]["cutoff_length_mm"] = None
    with pytest.raises(InputError, match=r"鉄筋\.杭\.cutoff\.cutoff_length_mm: 値が必要です"):
        detailing(data)


def test_the_head_anchorage_is_the_basic_anchorage_length_rounded_up_to_100_mm():
    found = detailing().anchorage
    # cb1 = 156 − 32／2 = 140.0; the bars' circle π(1200 − 2 × 156) = 2789.73, ／16 = 174.4; cb2 = (174.4 − 32)／2 = 71.2
    assert (found.clear_cover.value, found.pitch.value, found.half_gap.value, found.cb.value) == (140.0, 174.4, 71.2, 71.2)
    # no hoops inside the footing: those of the 2D zone, D19 × 1 組 @125
    assert (found.stirrup_zone, found.at.value, found.s.value) == ("杭頭2D区間", 286.5, 125.0)
    # Kc = 71.2／32 + 15 × 286.5／(125 × 32) = 2.225 + 1.074 = 3.30; αb = 0.75／3.30 + 0.2 = 0.427 → 0.5
    assert (found.kc.value, found.alpha_raw.value, found.alpha.value) == (3.3, 0.427, 0.5)
    # f'ck 24 of the footing: fbok 2.3, fbod 2.3／1.3 = 1.8; ld = 0.5 × 390／(4 × 1.8) × 32 = 866.7 → 867 (28φ) ＞ 20φ = 640
    assert (found.fck.value, found.fbok.value, found.fbod.value, found.fsyd.value) == (24.0, 2.3, 1.8, 390)
    assert (found.basic.value, found.bars, found.least.value, found.anchorage.value, found.length.value) == (
        867, 28, 640, 867, 900)


def test_the_hoops_inside_the_footing_give_the_anchorage_when_entered():
    data = sample()
    data["鉄筋"]["杭"]["hoops"]["footing"] = {"diameter_mm": 22, "sets": 2, "pitch_mm": 100.0}
    found = detailing(data).anchorage
    # At = 387.1 × 2 = 774.2; Kc = 71.2／32 + 15 × 774.2／(100 × 32) = 2.225 + 3.629 = 5.85; αb = 0.75／5.85 + 0.2 = 0.328
    assert (found.stirrup_zone, found.at.value, found.kc.value, found.alpha_raw.value, found.alpha.value) == (
        "フーチング内", 774.2, 5.85, 0.328, 0.5)
    data["鉄筋"]["杭"]["hoops"]["footing"]["pitch_mm"] = None
    with pytest.raises(InputError, match=r"鉄筋\.杭\.hoops\.footing\.pitch_mm: 値が必要です"):
        detailing(data)


def test_a_large_alpha_is_limited_to_1_and_20_phi_holds_a_short_anchorage():
    data = sample(main_bars={"diameter_mm": 16, "count": 8}, pure_cover_mm=60.0)  # ds = 60 + 19 + 8 = 87
    found = detailing(data).anchorage
    # cb1 = 87 − 8 = 79.0; π(1200 − 174)／8 = 402.9, cb2 = (402.9 − 16)／2 = 193.5 (rounded half up); cb = 79.0
    # Kc = 79.0／16 + 15 × 286.5／(125 × 16) = 4.9375 + 2.1488 = 7.09; αb = 0.75／7.09 + 0.2 = 0.306 → 0.5
    assert (found.cb.value, found.kc.value, found.alpha.value) == (79.0, 7.09, 0.5)
    # ld = 0.5 × 390／7.2 × 16 = 433.3 → 433 (28φ) ＞ 20φ = 320 → 500
    assert (found.basic.value, found.least.value, found.length.value) == (433, 320, 500)
    data = sample(main_bars={"diameter_mm": 38, "count": 40})  # ds = 121 + 19 + 19 = 159
    found = detailing(data).anchorage
    # cb1 = 159 − 19 = 140.0; π(1200 − 318)／40 = 69.3, cb2 = (69.3 − 38)／2 = 15.7 (15.65 up); Kc = 15.7／38 + 15 × 286.5／(125 × 38)
    # = 0.413 + 0.905 = 1.32; αb = 0.75／1.32 + 0.2 = 0.768; ld = 0.768 × 390／7.2 × 38 = 1580.8 → 1581 → 1600
    assert (found.half_gap.value, found.kc.value, found.alpha.value, found.basic.value, found.length.value) == (
        15.7, 1.32, 0.768, 1581, 1600)


def test_a_footing_strength_outside_the_bond_table_is_an_input_error():
    data = sample()
    data["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 25.0
    with pytest.raises(InputError, match=r"鉄筋\.フーチング\.concrete_strength_mpa: f'ck 25 の付着強度がありません"):
        detailing(data)


@pytest.mark.parametrize("path, message", [
    (("杭基礎", "場所打ち杭", "杭径"), "杭基礎.場所打ち杭.杭径: 値が必要です"),
    (("鉄筋", "杭", "main_bars", "count"), "鉄筋.杭.main_bars.count: 値が必要です"),
    (("鉄筋", "杭", "hoops", "zone_2d", "sets"), "鉄筋.杭.hoops.zone_2d.sets: 値が必要です"),
    (("鉄筋", "杭", "hoops", "lower", 0, "length_m"), "鉄筋.杭.hoops.lower[0].length_m: 値が必要です")])
def test_a_blank_item_is_an_input_error_naming_it(path, message):
    data = sample()
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = None
    with pytest.raises(InputError, match=message.replace(".", r"\.").replace("[", r"\[").replace("]", r"\]")):
        detailing(data)


def test_a_cover_reaching_the_centre_is_an_input_error():
    with pytest.raises(InputError, match=r"鉄筋\.杭\.pure_cover_mm: 杭径に対して大きすぎます"):
        detailing(sample(pure_cover_mm=570.0))


def test_the_pile_head_reaction_is_the_largest_compression_at_a_head_of_one_pile():
    from webpier.calc.pile_body import PileResponseError, PointForces, SectionForce

    def line(focus, point, smallest):
        return PointForces(focus, point, 0.0, SectionForce(0.0, 0.0, -1.0, 1), SectionForce(0.0, 0.0, smallest, 2))

    # the bundle of 3 piles: 9000／3 = 3000; of 2: 7000／2 = 3500 (the largest); a tip and a focus M are not read
    rows = [([line("N", "ITAN", -9000.0), line("N", "JTAN", -20000.0)], 3), ([line("N", "ITAN", -7000.0)], 2),
            ([line("M", "ITAN", -50000.0)], 1)]
    assert pile_head_reaction(rows) == Decimal(3500)
    with pytest.raises(PileResponseError, match="杭頭（ITAN）の軸方向圧縮力がありません"):
        pile_head_reaction([([line("N", "ITAN", 100.0)], 2)])


def test_the_minimum_bars_of_the_pile_head_reaction_are_the_sample_1():
    found = minimum_bars(parse_input(sample()), "線路方向", Decimal("7403.05"))
    # As' = 0.0104 × 7403.05 × 10³／(0.85 × 21.0 + 0.008 × 390) = 76991.72／20.97 = 3671.5 ＜ As = 12707.2
    assert (found.direction, found.pvmax.value, found.fck.value, found.fsyd.value) == ("線路方向", 7403.05, 21.0, 390)
    assert (found.required.value, found.section.bar_area.value, found.ok) == (3671.5, 12707.2, True)
    assert not minimum_bars(parse_input(sample()), "線路方向", Decimal("30000")).ok  # As' = 14878.4
