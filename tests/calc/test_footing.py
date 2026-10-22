"""0800 フーチングの応答値 (decision 60, CONTEXT.md): the pieces of 12.1 of one direction.

The expected values are the transcription tests/fixtures/example2/footing.json of the sample pages 244〜253 (its
notes list the workbook's formulas and its known error in q2) and hand calculations; nothing is computed by the code
under test. The trapezoid rows of 3) and the Md, Vd, La of the four non-seismic columns use the corrected
q2 (decision 60, ADR-0001) and are checked against the independent hand calculation footing_hand.json. The bearing
capacity (ex, B′, δ, Ir, Iq, βb, qvd, qd, Mmd) is 0612's (foundation_check.bearing_capacity), checked here with the
sample's Df and γe2 put into a basis of current.json. Columns with B′ > L (the 直角 ones but the seismic) have Be = L
in 0612 and B′ in the sample, so their qvd is not compared (decision 54); the 線路方向 seismic Mmd is 52617.46 from the
printed qd 2507.16 where the workbook's unrounded 2507.158 gives 52617.45 (ADR-0003).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from reaction_support import pier
from webpier.calc import foundation_check as fc
from webpier.calc import footing
from webpier.calc.foundation import calculate_foundation
from webpier.calc.foundation_check import PRESSURE
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.printed import LENGTH, LINE_LOAD, Printed

SAMPLE = json.loads((Path(__file__).parents[1] / "fixtures" / "example2" / "footing.json").read_text(
    encoding="utf-8"))
HAND = json.loads((Path(__file__).parents[1] / "fixtures" / "example2" / "footing_hand.json").read_text(
    encoding="utf-8"))
SANDY = {"地盤データ/層/1/土質区分": "砂質土", "地盤データ/層/0/単位体積重量/水中": 9.0}
DIRECTIONS = ("0800_longitudinal", "0800_transverse")
COLUMNS = ("safety_moment", "safety_shear", "short_term", "long_term", "seismic")
# Values that differ from the sample by its unrounded qd (footing_notes.md): the sample prints 52617.45.
ROUNDED_QD = {("0800_longitudinal", "seismic"): {"Mmd": 52617.46}}


def kn(value: float) -> Printed:
    return Printed(value, 2, "kN")


def knm(value: float) -> Printed:
    return Printed(value, 2, "kN m")


def metre(value: float) -> Printed:
    return Printed(value, 3, "m")


def pressure(value: float) -> Printed:
    return Printed(value, 2, "kN/m2")


def unit_weight(value: float) -> Printed:
    return Printed(value, 1, "kN/m3")


def geometry(direction: str) -> dict:
    return SAMPLE["directions"][direction]


def column(direction: str, key: str) -> dict:
    return SAMPLE["directions"][direction]["columns"][key]


def prepared(direction: str) -> fc.Basis:
    """0612's basis of current.json (sandy, cover 9.0 as pre/input.json) in the direction of the footing column."""
    p = pier(**SANDY)
    foundation, reaction = calculate_foundation(p), calculate_reaction(p)
    if direction == "0800_longitudinal":
        return fc.prepare(p, foundation, calculate_longitudinal(p, foundation, reaction), fc.LONGITUDINAL)
    return fc.prepare(p, foundation, calculate_transverse(p, foundation, reaction), fc.TRANSVERSE)


def sample_basis(direction: str) -> fc.Basis:
    """The same basis with the sample's Df 3.78 and γe2 (9.0 high water, 11.6 normal water)."""
    basis = prepared(direction)
    return replace(basis, depth=metre(3.78), normal=replace(basis.normal, unit_weight=unit_weight(11.6)),
                   high=replace(basis.high, unit_weight=unit_weight(9.0)))


# 1) 地盤反力形状 and the printed distribution of every sample column.
@pytest.mark.parametrize("key", COLUMNS)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_distribution_is_the_samples(direction, key):
    given, geo = column(direction, key), geometry(direction)
    found = footing.distribution(kn(given["Vd"]), knm(given["Md"]), metre(given["ex"]), metre(geo["B"]),
                                 metre(geo["L"]), pressure(given["qd"]), knm(given["Mmd"]))
    assert (found.case, found.apex.value, found.qd1.value, found.qd2.value, found.x1.value, found.x2.value) == (
        given["case"], given["apex"], given["qd1"], given["qd2"], given["X1"], given["X2"])


def test_case_2_is_a_triangle_shorter_than_the_footing():
    # Hand: B 7, L 9, Vd 10000, Md 15000 → ex 1.500 > B/6; apex 2·10000/(3·9·2.0) = 370.37 < qd 1000;
    # Mmd 7·10000/2 − 10000²/(2·1000·9) = 29444.44 > Md; X1 = 2·10000/(370.37·9) = 6.000.
    found = footing.distribution(kn(10000), knm(15000), metre(1.5), metre(7), metre(9), pressure(1000),
                                 knm(29444.44))
    assert (found.case, found.apex.value, found.qd1.value, found.qd2.value, found.x1.value, found.x2.value) == (
        2, 370.37, 370.37, 0.0, 6.0, 0.0)


def test_case_3_is_a_block_with_a_triangle_when_the_apex_exceeds_qd():
    # Hand: as above with qd 300 < apex 370.37; Mmd 35000 − 10000²/(2·300·9) = 16481.48 > Md 15000;
    # X2 = √(12·7·10000/2700 − 12·10000²/2700² − 24·15000/2700) = √(311.111 − 164.609 − 133.333) = 3.629;
    # X1 = 10000/2700 − 3.629/2 = 1.889. Equilibrium: 300 × (1.889 + 3.629/2) × 9 = 9999.5 ≒ Vd.
    found = footing.distribution(kn(10000), knm(15000), metre(1.5), metre(7), metre(9), pressure(300),
                                 knm(16481.48))
    assert (found.case, found.apex.value, found.qd1.value, found.qd2.value, found.x1.value, found.x2.value) == (
        3, 370.37, 300.0, 0.0, 1.889, 3.629)


def test_case_4_is_a_block_when_md_exceeds_mmd():
    # Hand: qd 300, Md 17000 > Mmd 16481.48; X1 = 10000/(300·9) = 3.704.
    found = footing.distribution(kn(10000), knm(17000), metre(1.7), metre(7), metre(9), pressure(300),
                                 knm(16481.48))
    assert (found.case, found.qd1.value, found.qd2.value, found.x1.value, found.x2.value) == (4, 300.0, 0.0, 3.704,
                                                                                               0.0)


def test_ex_at_b_over_6_is_still_case_1():
    # Hand: B 6, Vd 6000, Md 6000 → ex 1.000 = B/6: qd1 = 6000/54 × 2 = 222.22, qd2 = 0.00, X1 = B.
    found = footing.distribution(kn(6000), knm(6000), metre(1.0), metre(6), metre(9), pressure(5000),
                                 knm(99999.99))
    assert (found.case, found.qd1.value, found.qd2.value, found.x1.value) == (1, 222.22, 0.0, 6.0)


# The bearing capacity of each column is 0612's formula with the column's factors and water level.
@pytest.mark.parametrize("key", COLUMNS)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_bearing_capacity_is_the_samples_with_its_df_and_gamma_e2(direction, key):
    given, basis = column(direction, key), sample_basis(direction)
    cover = getattr(basis, footing.WATER[key])
    found = fc.bearing_capacity(basis, footing.FACTORS[key], cover, kn(given["Vd"]), kn(given["Hd"]),
                                knm(given["Md"]))
    assert (found.ex.value, found.b_effective.value, found.area_effective.value, found.delta.value) == (
        given["ex"], given["B_eff"], given["A_eff"], given["delta"])
    assert (cover.unit_weight.value, found.i_gamma.value, found.i_q.value, found.beta_b.value) == (
        given["gamma_e2"], given["Ir"], given["Iq"], given["beta_b"])
    assert footing.FACTORS[key].f_gamma.value == footing.FACTORS[key].f_q.value == given["fr"]
    assert footing.shape_alpha(found.b_effective, basis.l).value == given["alpha_b"]
    if given["B_eff"] > geometry(direction)["L"]:
        return  # B′ > L: the sample's Be is B′, 0612's L (decision 54)
    expected = {**given, **ROUNDED_QD.get((direction, key), {})}
    assert (found.term_gamma.value, found.term_q.value, found.qvd.value, found.qd_unlimited.value,
            found.mmd.value) == (expected["term_gamma"], expected["term_q"], expected["qvd"], expected["qd"],
                                 expected["Mmd"])


def test_the_seismic_factors_are_one():
    factors = footing.FACTORS["seismic"]
    assert (factors.f_gamma.value, factors.f_q.value) == (1.0, 1.0)
    assert footing.WATER == {"safety_moment": "high", "safety_shear": "high", "short_term": "high",
                             "long_term": "normal", "seismic": "normal"}


# 2) 有効幅
@pytest.mark.parametrize("direction,cover_mm,d", [("0800_longitudinal", 100, 2.6), ("0800_transverse", 127, 2.573)])
def test_the_effective_width_is_the_column_and_the_overhangs_within_d(direction, cover_mm, d):
    geo = geometry(direction)
    found = footing.effective_width(metre(geo["column_across"]), metre(geo["overhang_across"]),
                                    metre(geo["overhang_across"]), metre(SAMPLE["geometry"]["H6"]),
                                    Printed(cover_mm, 1, "mm"))
    assert (found.d.value, found.left_effective.value, found.right_effective.value, found.be.value,
            found.full.value) == (d, geo["overhang_across"], geo["overhang_across"], geo["be"], geo["full_width"])


def test_a_thin_footing_limits_the_effective_overhangs_to_d():
    # Hand: d = 1.000 − 0.100 = 0.900 < 2.250; be = 0.900 + 4.500 + 0.900 = 6.300 ≦ 9.000; the right overhang
    # 0.500 is shorter than d and counts whole.
    found = footing.effective_width(metre(4.5), metre(2.25), metre(0.5), metre(1.0), Printed(100, 1, "mm"))
    assert (found.d.value, found.left_effective.value, found.right_effective.value, found.be.value,
            found.full.value) == (0.9, 0.9, 0.5, 5.9, 7.25)


# 4) 自重・上載土, 5) 浮力
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_self_weight_rows_are_the_samples(direction):
    geo = geometry(direction)
    found = footing.self_weight(metre(SAMPLE["geometry"]["df"]), metre(SAMPLE["geometry"]["H6"]), metre(geo["L1"]),
                                unit_weight(18.0), unit_weight(24.5))
    for row, given in ((found.overburden, geo["self_weight"]["overburden"]),
                       (found.footing, geo["self_weight"]["footing"])):
        assert (row.height.value, row.length.value, row.volume.value, row.unit_weight.value, row.w.value,
                row.x.value, row.m.value) == (given["height"], given["length"], given["V"], given["gamma"],
                                              given["W"], given["x"], given["M"])
    assert (found.w.value, found.m.value) == (geo["self_weight"]["W"], geo["self_weight"]["M"])


@pytest.mark.parametrize("level", ("high", "normal", "low"))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_buoyancy_rows_are_the_samples(direction, level):
    geo, given = geometry(direction), geometry(direction)["buoyancy"][level]
    found = footing.buoyancy(metre(given["water"]), metre(geo["L1"]))
    assert (found.height.value, found.length.value, found.volume.value, found.unit_weight.value, found.w.value,
            found.x.value, found.m.value) == (given["water"], given["length"], given["V"], given["gamma"],
                                              given["W"], given["x"], given["M"])


# 3) the Case 4 block ends inside the overhang (the seismic rows of the sample).
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_block_inside_the_overhang_is_one_uniform_segment(direction):
    given, geo = column(direction, "seismic"), geometry(direction)
    dist = footing.distribution(kn(given["Vd"]), knm(given["Md"]), metre(given["ex"]), metre(geo["B"]),
                                metre(geo["L"]), pressure(given["qd"]), knm(given["Mmd"]))
    (segment,) = footing.ground_reaction(dist, metre(geo["L1"]))
    assert (segment.q1.value, segment.uniform, segment.length.value, segment.w.value, segment.x.value,
            segment.m.value) == (given["reaction"]["q1"], True, given["reaction"]["length"],
                                 given["reaction"]["W"], given["reaction"]["x"], given["reaction"]["M"])


# 6) 7) the design forces of the seismic column: full width, be, self weight, the normal-water buoyancy.
@pytest.mark.parametrize("direction,vd,la", [("0800_longitudinal", 1708.69, 1.843), ("0800_transverse", 2233.73, 1.809)])
def test_the_seismic_design_forces_take_the_normal_water(direction, vd, la):
    # The sample's 7) takes the high water for the seismic Vd (1731.89 / 2258.03); decision 60 the normal water
    # as its 6) does: 1870.34 − 219.75 + 58.10 = 1708.69, La = 3149.81 / 1708.69 = 1.843.
    given, geo = column(direction, "seismic"), geometry(direction)
    weight = footing.self_weight(metre(SAMPLE["geometry"]["df"]), metre(SAMPLE["geometry"]["H6"]), metre(geo["L1"]),
                                 unit_weight(18.0), unit_weight(24.5))
    water = footing.buoyancy(metre(geo["buoyancy"]["normal"]["water"]), metre(geo["L1"]))
    found = footing.section_forces(knm(given["reaction"]["M"]), Printed(given["reaction"]["W"], 2, "kN/m"),
                                   metre(geo["full_width"]), metre(geo["be"]), weight, water)
    assert (found.m_full.value, found.m_per_m.value, found.md.value) == (given["M_full"], given["M_per_m"],
                                                                         given["Md_design"])
    assert (found.v_full.value, found.v_per_m.value, found.vd.value, found.la.value) == (given["V_full"],
                                                                                         given["V_per_m"], vd, la)


# The seismic action: the first output step whose V reaches Rvd, of the Case with the largest |Md|.
def step(case_index, step_number, v, h, m, rvd, name=None):
    return footing.FoundationStep(case_index, name or f"Case{case_index + 1}", 7, step_number, v, h, m,
                                  3236.74, 3296.9, rvd, 54120.2, 0.081)


STEPS = (step(0, 1, 16825.97, 0.0, 580.25, 543358.71), step(0, 2, 16825.97, -5747.86, 52784.78, 22069.94),
         step(0, 3, 16825.97, -5901.07, 54168.43, 16655.87), step(0, 4, 16825.97, -5949.26, 54514.06, 16655.87))
# The αf of Case1〜4 by index, as the four 照査パターン (ρm, αf) of 0710 give them (decision 76).
ALPHA_F = tuple(Printed(alpha_f, 1, "") for alpha_f in (1.0, 1.0, 2.0, 2.0))


def test_the_seismic_action_is_the_first_step_at_rvd():
    found = footing.seismic_action(STEPS, ALPHA_F)
    assert (found.case_index, found.case_name, found.step) == (0, "Case1", 3)
    assert (found.vd.value, found.hd.value, found.md.value) == (16825.97, 5901.07, 54168.43)
    assert footing.seismic_action(tuple(reversed(STEPS)), ALPHA_F) == found


def test_the_case_with_the_largest_md_at_rvd_is_taken():
    other = (step(1, 1, 16825.97, 0.0, 580.25, 543358.71), step(1, 2, 16825.97, 5901.07, -54268.43, 16655.87),
             step(1, 3, 16825.97, 5949.26, -54614.06, 16655.87))
    found = footing.seismic_action(STEPS + other, ALPHA_F)
    assert (found.case_index, found.case_name, found.step, found.hd.value, found.md.value) == (1, "Case2", 2, 5901.07,
                                                                                               54268.43)
    tie = (step(1, 1, 16825.97, 0.0, 580.25, 543358.71), step(1, 2, 16825.97, 5901.07, -54168.43, 16655.87))
    assert footing.seismic_action(STEPS + tie, ALPHA_F).case_index == 0


def test_a_case_of_alpha_f_2_is_not_a_candidate():
    # Decision 76: Case3 (αf 2.0) reaches Rvd with a larger |Md| but is for the superstructure, not the foundation.
    larger = (step(2, 1, 16825.97, 0.0, 580.25, 543358.71), step(2, 2, 16825.97, 5901.07, -99999.0, 16655.87))
    assert footing.seismic_action(STEPS + larger, ALPHA_F).case_index == 0
    with pytest.raises(footing.StepsError, match="αf=1.0 のどの Case も Rvd到達ステップがありません"):
        footing.seismic_action(larger, ALPHA_F)


def test_a_case_outside_the_combinations_is_an_error():
    with pytest.raises(footing.StepsError, match=r"Case5 の Case の番号 4 が組合せ（4件）にありません"):
        footing.seismic_action(STEPS + (step(4, 1, 16825.97, 0.0, 580.25, 543358.71),), ALPHA_F)
    with pytest.raises(footing.StepsError, match="番号 -1 が"):
        footing.seismic_action((step(-1, 1, 16825.97, 0.0, 580.25, 543358.71),), ALPHA_F)


def test_a_case_that_never_reaches_rvd_is_not_a_candidate():
    never = (step(1, 1, 16825.97, 0.0, 580.25, 543358.71), step(1, 2, 16825.97, 9000.0, 99999.0, 20000.0))
    assert footing.seismic_action(STEPS + never, ALPHA_F).case_index == 0
    with pytest.raises(footing.StepsError, match="どの Case も Rvd到達ステップがありません"):
        footing.seismic_action(never, ALPHA_F)


def test_an_upward_or_zero_vd_at_rvd_is_an_error():
    rows = (step(0, 1, 16825.97, 0.0, 580.25, 543358.71), step(0, 2, 0.0, 5000.0, 50000.0, -1.0))
    with pytest.raises(footing.StepsError, match=r"Case1 のステップ 2 の鉛直力 V が 0 以下です（0\.0 kN）"):
        footing.seismic_action(rows, ALPHA_F)


# 3) 6) 7) the trapezoid rows of the four non-seismic columns, with the corrected q2 (hand calculation).
@pytest.mark.parametrize("key", COLUMNS[:4])
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_trapezoid_rows_are_the_hand_calculation(direction, key):
    given, geo = column(direction, key), geometry(direction)
    hand = HAND["directions"][direction]["columns"][key]
    dist = footing.distribution(kn(given["Vd"]), knm(given["Md"]), metre(given["ex"]), metre(geo["B"]),
                                metre(geo["L"]), pressure(given["qd"]), knm(given["Mmd"]))
    (segment,) = footing.ground_reaction(dist, metre(geo["L1"]))
    assert (segment.q1.value, segment.q2.value, segment.uniform, segment.length.value, segment.w.value,
            segment.x.value, segment.m.value) == (hand["reaction"]["q1"], hand["reaction"]["q2"],
                                                  given["qd1"] == given["qd2"], hand["reaction"]["length"],
                                                  hand["reaction"]["W"], hand["reaction"]["x"], hand["reaction"]["M"])
    weight = footing.self_weight(metre(SAMPLE["geometry"]["df"]), metre(SAMPLE["geometry"]["H6"]), metre(geo["L1"]),
                                 unit_weight(18.0), unit_weight(24.5))
    level = footing.UPLIFT[key]
    water = footing.buoyancy(metre(geo["buoyancy"][level]["water"]), metre(geo["L1"]))
    found = footing.section_forces(segment.m, segment.w, metre(geo["full_width"]), metre(geo["be"]), weight, water)
    assert (found.m_full.value, found.m_per_m.value, found.md.value, found.v_full.value, found.v_per_m.value,
            found.vd.value, found.la.value) == (hand["M_full"], hand["M_per_m"], hand["Md_design"], hand["V_full"],
                                                hand["V_per_m"], hand["Vd_design"], hand["La"])


def test_the_uplift_is_the_high_water_for_safety_and_the_normal_water_otherwise():
    assert footing.UPLIFT == {"safety_moment": "high", "safety_shear": "high", "short_term": "normal",
                              "long_term": "normal", "seismic": "normal"}


def test_a_triangle_longer_than_the_overhang_is_one_sloping_segment():
    # Hand (footing_notes.md, 直角 seismic of WebPier's input): Case 2, apex 1250.95, X1 3.843 > L1 2.250:
    # q2 = 1250.95 × (1 − 2.25/3.843) = 518.54, W = 1990.68, x = 1.280, M = 2548.07.
    hand = HAND["directions"]["0800_transverse"]["seismic_own_input"]
    dist = footing.distribution(kn(hand["Vd"]), knm(hand["Md"]), metre(hand["ex"]), metre(9), metre(7),
                                pressure(hand["qd"]), knm(hand["Mmd"]))
    assert (dist.case, dist.apex.value, dist.qd1.value, dist.x1.value) == (2, hand["apex"], hand["qd1"], hand["X1"])
    (segment,) = footing.ground_reaction(dist, metre(2.25))
    (expected,) = hand["segments"]
    assert (segment.q1.value, segment.q2.value, segment.uniform, segment.length.value, segment.w.value,
            segment.x.value, segment.m.value) == (expected["q1"], expected["q2"], False, expected["length"],
                                                  expected["W"], expected["x"], expected["M"])


def test_a_case_3_profile_within_the_overhang_has_a_block_and_a_triangle():
    # Hand: qd 300, L 9, B 7: X1 1.889, X2 3.629 (test_case_3 above); overhang L1 3.000 covers the block and
    # 1.111 of the triangle: block W = 300 × 1.889 = 566.70, x = (3.000 − 1.889) + 1.889/2 = 2.0555 → 2.056,
    # M = 566.70 × 2.056 = 1165.14; triangle part q2 = 300 × (1 − 1.111/3.629) = 208.16, W = (300 + 208.16)/2 × 1.111 = 282.28,
    # x = 0 + 1.111 × (600 + 208.16)/(3 × 508.16) = 0.589, M = 166.26.
    dist = footing.distribution(kn(10000), knm(15000), metre(1.5), metre(7), metre(9), pressure(300),
                                knm(16481.48))
    block, triangle = footing.ground_reaction(dist, metre(3.0))
    assert (block.q1.value, block.q2.value, block.uniform, block.length.value, block.w.value, block.x.value,
            block.m.value) == (300.0, 300.0, True, 1.889, 566.7, 2.056, 1165.14)
    assert (triangle.q1.value, triangle.q2.value, triangle.uniform, triangle.length.value, triangle.w.value,
            triangle.x.value, triangle.m.value) == (300.0, 208.16, False, 1.111, 282.28, 0.589, 166.26)


def test_an_overhang_beyond_the_profile_carries_nothing_more():
    # Case 2 with X1 6.000 and an overhang of 6.500: one segment of 6.000 (q2 = 0), nothing after it.
    dist = footing.distribution(kn(10000), knm(15000), metre(1.5), metre(7), metre(9), pressure(1000),
                                knm(29444.44))
    (segment,) = footing.ground_reaction(dist, metre(6.5))
    assert (segment.q2.value, segment.length.value, segment.x.value) == (0.0, 6.0, 4.5)


def test_a_block_longer_than_the_overhang_gives_one_segment_and_a_zero_profile_the_mid_point():
    """ground_reaction: the profile is cut at L1 (a Case 3 block of 3.0 m on a 2.0 m overhang gives one uniform
    segment, the triangle beyond it nothing); a zero pressure has its centroid at the segment's middle."""
    block = footing.Distribution(3, PRESSURE(300), PRESSURE(300), PRESSURE(0), LENGTH(3.0), LENGTH(1.0))
    segments = footing.ground_reaction(block, LENGTH(2.0))
    assert [(segment.length.value, segment.uniform, segment.x.value) for segment in segments] == [(2.0, True, 1.0)]
    empty = footing.Distribution(4, PRESSURE(0), PRESSURE(0), PRESSURE(0), LENGTH(1.0), LENGTH(0))
    (segment,) = footing.ground_reaction(empty, LENGTH(2.0))
    assert (segment.w.value, segment.x.value, segment.m.value) == (0.0, 1.5, 0.0)


def test_a_design_shear_force_that_is_not_positive_is_an_input_error():
    weight = footing.self_weight(LENGTH(2.0), LENGTH(2.7), LENGTH(2.15), Printed(18.0, 1, "kN/m3"),
                                 Printed(24.5, 1, "kN/m3"))
    water = footing.buoyancy(LENGTH(3.78), LENGTH(2.15))
    with pytest.raises(InputError, match="設計せん断力 Vd が 0 以下"):
        footing.section_forces(footing.MOMENT_PER_M(10.0), LINE_LOAD(10.0), LENGTH(9.0), LENGTH(9.0), weight, water)
