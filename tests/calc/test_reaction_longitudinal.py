"""0600 longitudinal forces on the girders and bearings: Example2 07 7-4 to 7-13 and hand calculations."""

from decimal import Decimal

import pytest

from reaction_support import D, END_SLOTS, ORIGIN_SLOTS, example2, pier, q, value
from webpier.calc.reaction import calculate_reaction
from webpier.calc.reaction.longitudinal import BearingType, LongitudinalCase
from webpier.calc.reaction.longitudinal import LAYOUT_CASES, BrakeForces
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT

C = LongitudinalCase
EX = {}
for section in ("07_7-4_longitudinal_girder_horizontal", "07_7-5_seismic_train_inertia_and_bearing_0.8LR",
                "07_7-6_bearing_1.0LR_service", "07_7-7_bearing_safety_1.0LR_1.23B",
                "07_7-8_bearing_safety_1.1LR_1.23B", "07_7-9_bearing_safety_1.0LR_1.35B",
                "07_7-10_bearing_safety_1.0LR", "07_7-11_bearing_restorability_1.0LR_1.23B",
                "07_7-12_bearing_restorability_1.0LR", "07_7-13_bearing_seismic_and_summary"):
    EX.update(example2(section))

PREFIX = {
    C.SERVICE_LR08: ("bearing.serviceability_crack.0_8LR", "serviceability.0_8LR_1"),
    C.SERVICE_LR10: ("bearing.serviceability_crack_need.1_0LR", "serviceability.1_0LR_2"),
    C.SAFETY_LR10_B10: ("bearing.safety.1_0LR_1_23B", "safety.1_0LR_1_23B"),
    C.SAFETY_LR11_B10: ("bearing.safety.1_1LR_1_23B", "safety.1_1LR_1_23B"),
    C.SAFETY_LR10_B11: ("bearing.safety.1_0LR_1_35B", "safety.1_0LR_1_35B"),
    C.SAFETY_LR10: ("bearing.safety.1_0LR", "safety.1_0LR"),
    C.RESTORABILITY_LR10_B10: ("bearing.restorability.1_0LR_1_23B", "restorability.1_0LR_1_23B"),
    C.RESTORABILITY_LR10: ("bearing.restorability.1_0LR", "restorability.1_0LR"),
}

# Rm where Example2 used unrounded reactions (RB = 272.4668, RD = 25.0811) instead of the printed 272.47 / 25.08.
# Our value is the hand calculation from the printed operands of the same formula line.
RM_FROM_PRINTED = {
    # 7-7: 7678 + 1.35 × 272.47 × 2 × (1 + 0.222) = 8576.98752 -> 8576.99 (Example2 8576.98 from RB 272.4668)
    ("bearing.safety.1_0LR_1_23B", "movable"): 8576.99,
    # 7-8: 7678 + 1.23 × 272.47 × 2 × 1.222 = 8497.07752 -> 8497.08 (Example2 8497.07 from RB 272.4668)
    ("bearing.safety.1_1LR_1_23B", "movable"): 8497.08,
    # 7-9 (decision 119: the train without impact, as its label "1.23複線L"; Example2's formula has (1 + 0.222)):
    # 7678 + 1.23 × 272.47 × 2 = 8348.2762 -> 8348.28. 7678 = 1.1 × 5740 + 1.2 × 520 + 740, which is also
    # Example2's Rm 8497.07 less 1.23 × 272.4668 × 2 × 1.222.
    ("bearing.safety.1_0LR_1_35B", "movable"): 8348.28,
    # 7-11: 7000 + 1.23 × 272.47 × 2 × 1.222 = 7819.07752 -> 7819.08 (Example2 7819.07 from RB 272.4668)
    ("bearing.restorability.1_0LR_1_23B", "movable"): 7819.08,
    # 7-6: 2370 + 25.08 × 2 × (1 + 0.391) = 2439.77256 -> 2439.77 (Example2 2439.78 from RD 25.0811)
    ("bearing.serviceability_crack_need.1_0LR", "fixed"): 2439.77,
    # 7-8: 2758 + 1.23 × 25.08 × 2 × 1.521 = 2851.84083 -> 2851.84. Example2 prints 2851.85, which the
    # unrounded RD does not give either (2851.8449); not reproducible from the page.
    ("bearing.safety.1_1LR_1_23B", "fixed"): 2851.84,
    # 7-9 (decision 119): 2758 + 1.23 × 25.08 × 2 = 2819.6968 -> 2819.70. 2758 = 1.1 × 1860 + 1.2 × 260 + 400.
    ("bearing.safety.1_0LR_1_35B", "fixed"): 2819.70,
    # 7-11: 2520 + 1.23 × 25.08 × 2 × 1.521 = 2613.84083 -> 2613.84 (Example2 2613.85; unrounded RD gives 2613.8449)
    ("bearing.restorability.1_0LR_1_23B", "fixed"): 2613.84,
}


def longitudinal(p=None):
    return calculate_reaction(p or pier()).longitudinal


def test_example2_girder_forces_7_4_7_5():
    result = longitudinal()
    for girder, n in ((result.origin, "1"), (result.end, "2")):
        assert girder.long_rail.value == EX[f"long_rail.a.T{n}"]
        assert girder.long_rail_service.value == EX[f"long_rail.b.T{n}"]
        assert girder.braking.value == EX[f"braking.T{n}"]
        assert girder.starting.value == EX[f"starting.T{n}"]
        assert girder.braking_adopted.value == EX[f"braking.T{n}"]  # braking governs
        assert girder.seismic_girder.value == EX[f"seismic_inertia.T{n}"]
        assert girder.seismic_train.value == EX[f"seismic_train_inertia.T{n}"]
    assert (result.origin.length.value, result.end.length.value) == (20.0, 10.0)


# Decision 119: braking-governed 1.0 LR + 1.35B takes the train without impact in Rm (its label "1.23複線L"), so
# Example2 7-9's Rm, which has (1 + i), is not compared; its T1, T2 and T/n do not depend on Rm.
WITHOUT_IMPACT = {C.SAFETY_LR10_B11}


@pytest.mark.parametrize("case", list(PREFIX), ids=lambda case: case.name)
def test_example2_bearing_cases_7_5_to_7_12(case):
    prefix, summary = PREFIX[case]
    forces = longitudinal().case(case)
    movable, fixed = forces.origin, forces.end
    assert (movable.bearing, fixed.bearing) == (BearingType.MOVABLE, BearingType.FIXED)
    assert movable.applied.value == EX[f"{prefix}.T1"]
    assert fixed.applied.value == EX[f"{prefix}.T2"]
    if case in WITHOUT_IMPACT:
        assert movable.share.value == EX[f"{prefix}.movable.T_over_n"]
        assert movable.friction_floor.value == EX[f"{prefix}.movable.0.1_T_over_n"]
        assert fixed.share.value == EX[f"{prefix}.fixed.T_over_n"]
        return
    assert movable.vertical.value == RM_FROM_PRINTED.get((prefix, "movable"), EX[f"{prefix}.movable.Rm"])
    assert movable.share.value == EX[f"{prefix}.movable.T_over_n"]
    assert movable.friction.value == EX[f"{prefix}.movable.mu_Rm"]
    assert movable.friction_floor.value == EX[f"{prefix}.movable.0.1_T_over_n"]
    assert movable.force.value == EX[f"{prefix}.movable.H"]
    assert movable.fixed_candidate is None
    assert fixed.vertical.value == RM_FROM_PRINTED.get((prefix, "fixed"), EX[f"{prefix}.fixed.Rm"])
    assert fixed.fixed_candidate.value == EX[f"{prefix}.fixed.T_minus_half_mu_Rm"]
    assert fixed.share.value == EX[f"{prefix}.fixed.T_over_n"]
    assert fixed.force.value == EX[f"{prefix}.fixed.H"]
    assert (fixed.friction, fixed.friction_floor) == (None, None)
    assert forces.total.value == EX[f"bearing_summary.{summary}.total"]
    assert movable.force.value == EX[f"bearing_summary.{summary}.start_girder"]
    assert fixed.force.value == EX[f"bearing_summary.{summary}.end_girder"]


def test_example2_seismic_bearings_7_13():
    result = longitudinal()
    for forces, key in ((result.seismic_girder, "seismic_girder"), (result.seismic_train, "seismic_train")):
        assert forces.origin.applied.value == EX[f"bearing.{key}.T1"]
        assert forces.origin.force.value == EX[f"bearing.{key}.movable.H"]  # movable: T/n, no upper limit
        assert forces.end.applied.value == EX[f"bearing.{key}.T2"]
        assert forces.end.force.value == EX[f"bearing.{key}.fixed.H"]  # fixed: the whole T
    assert result.seismic_girder.total.value == EX["bearing_summary.seismic.EQ_girder.total"]
    assert result.seismic_train.total.value == EX["bearing_summary.seismic.EQ_train.total"]


def test_example2_combination_factors():
    case = longitudinal().case(C.SAFETY_LR10_B11)
    # 1.231 × 1.0 = 1.231 -> 1.23 on the train, 1.231 × 1.1 = 1.3541 -> 1.35 on braking (07 7-9).
    assert (case.origin.live_factor.value, case.origin.brake_factor.value) == (1.23, 1.35)
    assert longitudinal().case(C.SAFETY_LR10_B10).origin.live_factor.value == 1.35
    assert longitudinal().case(C.SAFETY_LR10).origin.live_factor is None


def hand_case(case, side_loads, far_loads, r_pier, r_far, tracks, mu, bearing, girder):
    """One bearing case by hand: (T, Rm, T/n, μRm, μT/n, T−½μRm, H)."""
    lr_factor, service_rail, brake, d1f, d2f, live, impact, snow = case
    t = q(lr_factor * (girder["lr_service"] if service_rail else girder["lr"]) + (brake or 0) * girder["b"], 2)
    loads = side_loads if bearing == "movable" else far_loads
    r = r_pier if bearing == "movable" else r_far
    rm = q(d1f * loads["d1"] + d2f * loads["d2"] + (live * r * tracks * (1 + impact) if live else 0) + loads[snow], 2)
    share = q(t / 2, 2)
    if bearing == "movable":
        friction, floor = q(mu * rm, 2), q(mu * share, 2)
        return t, rm, share, friction, floor, None, min(share, max(friction, floor))
    candidate = q(t - mu * rm / 2, 2)
    return t, rm, share, None, None, candidate, max(candidate, share)


def actual_case(force):
    def v(x):
        return None if x is None else value(x)
    return (value(force.applied), value(force.vertical), value(force.share), v(force.friction),
            v(force.friction_floor), v(force.fixed_candidate), value(force.force))


def test_braking_case_takes_the_train_without_impact_by_hand():
    """Decision 119: Rm = 1.1D1 + 1.2D2 + 1.0 × ρ × L (+ S10), without (1 + i), in 1.0 LR + 1.35B (Example2 07 7-9).
    Movable B: Rm = 1.1 × 5740 + 1.2 × 520 + 1.23 × 272.47 × 2 + 740 = 8348.2762 -> 8348.28,
    μRm = 834.83, T/n = 616.00 / 2 = 308.00, H = 308.00. Fixed C (far bearing D): Rm = 1.1 × 1860 + 1.2 × 260
    + 1.23 × 25.08 × 2 + 400 = 2819.6968 -> 2819.70, T − ½μRm = 329.60 − 0.05 × 2819.70 = 188.615 -> 188.62,
    T/n = 164.80, H = 188.62. Total 496.62."""
    forces = longitudinal().case(C.SAFETY_LR10_B11)
    b = {"d1": D(5740), "d2": D(520), "S10": D(740)}
    dd = {"d1": D(1860), "d2": D(260), "S10": D(400)}
    case = (D(1), False, D("1.35"), D("1.1"), D("1.2"), D("1.23"), D(0), "S10")
    expected_origin = hand_case(case, b, None, D("272.47"), None, D(2), D("0.1"), "movable",
                                {"lr": D(400), "b": D(160)})
    expected_end = hand_case(case, None, dd, None, D("25.08"), D(2), D("0.1"), "fixed", {"lr": D(200), "b": D(96)})
    assert actual_case(forces.origin) == expected_origin
    assert actual_case(forces.end) == expected_end
    assert expected_origin[1] == D(str(RM_FROM_PRINTED[("bearing.safety.1_0LR_1_35B", "movable")]))
    assert expected_end[1] == D(str(RM_FROM_PRINTED[("bearing.safety.1_0LR_1_35B", "fixed")]))
    assert (expected_origin[-1], expected_end[-1]) == (D("308.00"), D("188.62"))
    assert value(forces.total) == D("496.62")


def test_example4_braking_case_takes_the_train_without_impact_by_hand():
    """Decision 119 on Example橋脚4, placing ①, 1.0 LR + 1.1B (ρf = 1.0).
    End (fixed; far movable bearing): Rm = 1.1 × 4250 + 1.2 × 1050 + 1.0 × 832.29 × 2 = 4675 + 1260 + 1664.58
    = 7599.58; T = 1.1 × 382.5 + 500 = 920.75; T − ½μRm = 920.75 − 0.5 × 0.1 × 7599.58 = 540.771 -> 540.77 = H.
    Origin (movable): T/n = (1.1 × 142.5 + 160) / 2 = 158.375 -> 158.38 < μRm = 0.1 × (1.1 × 1710 + 1.2 × 470
    + 379.44 × 2) = 320.39, so H = 158.38. Total 699.15."""
    pier4 = parse_input(load_json(EXAMPLE4_INPUT.read_bytes()))
    forces = calculate_reaction(pier4).longitudinal.case(C.SAFETY_LR10_B11)
    origin, end = forces.origin, forces.end
    assert (origin.bearing, end.bearing) == (BearingType.MOVABLE, BearingType.FIXED)
    assert value(end.vertical) == D("7599.58")
    assert value(end.fixed_candidate) == D("540.77")
    assert value(end.force) == D("540.77")
    assert value(origin.friction) == D("320.39")
    assert value(origin.force) == D("158.38")
    assert value(forces.total) == D("699.15")


B_LOADS = {"d1": D(5740), "d2": D(520), "S10": D(740)}  # Example2 movable B (07 7-7)
D_LOADS = {"d1": D(1860), "d2": D(260), "S10": D(400)}  # Example2 far movable D of the fixed C


def test_reduced_dead_load_braking_case_by_hand():
    """Decision 120: 0.9D1 + 0.8D2 + 1.0L (without impact, decision 119) + S10 + 1.0LR + 1.35B (Example橋脚4
    III-45〜57 ③). T1 = 1.0 × 400 + 1.35 × 160 = 616.00, T2 = 200 + 1.35 × 96 = 329.60.
    Movable B: Rm = 0.9 × 5740 + 0.8 × 520 + 1.23 × 272.47 × 2 + 740 = 5166 + 416 + 670.2762 + 740 = 6992.2762
    -> 6992.28, μRm = 699.228 -> 699.23 > T/n = 308.00, so H1 = 308.00. Fixed C (far D): Rm = 0.9 × 1860
    + 0.8 × 260 + 1.23 × 25.08 × 2 + 400 = 1674 + 208 + 61.6968 + 400 = 2343.6968 -> 2343.70,
    T − ½μRm = 329.60 − 0.05 × 2343.70 = 329.60 − 117.185 = 212.415 -> 212.42 ≥ T/n = 164.80, H2 = 212.42.
    Total 520.42."""
    forces = longitudinal().case(C.SAFETY_LR10_B11_REDUCED)
    case = (D(1), False, D("1.35"), D("0.9"), D("0.8"), D("1.23"), D(0), "S10")
    expected_origin = hand_case(case, B_LOADS, None, D("272.47"), None, D(2), D("0.1"), "movable",
                                {"lr": D(400), "b": D(160)})
    expected_end = hand_case(case, None, D_LOADS, None, D("25.08"), D(2), D("0.1"), "fixed",
                             {"lr": D(200), "b": D(96)})
    assert actual_case(forces.origin) == expected_origin
    assert actual_case(forces.end) == expected_end
    assert expected_origin == (D("616.00"), D("6992.28"), D("308.00"), D("699.23"), D("30.80"), None, D("308.00"))
    assert expected_end == (D("329.60"), D("2343.70"), D("164.80"), None, None, D("212.42"), D("212.42"))
    assert (value(forces.origin.live_factor), value(forces.origin.brake_factor)) == (D("1.23"), D("1.35"))
    assert value(forces.total) == D("520.42")


def test_reduced_dead_load_long_rail_case_by_hand():
    """Decision 120: 0.9D1 + 0.8D2 + 1.0(L + I) + S10 + 1.1LR + 1.23B (Example橋脚4 III-45〜57 ⑤).
    T1 = 1.1 × 400 + 1.23 × 160 = 440 + 196.8 = 636.80, T2 = 1.1 × 200 + 1.23 × 96 = 220 + 118.08 = 338.08.
    Movable B: Rm = 5166 + 416 + 1.23 × 272.47 × 2 × 1.222 + 740 = 5166 + 416 + 819.0775164 + 740 = 7141.0775
    -> 7141.08, μRm = 714.11 > T/n = 318.40, H1 = 318.40. Fixed C: Rm = 1674 + 208 + 1.23 × 25.08 × 2 × 1.521
    + 400 = 1674 + 208 + 93.8408328 + 400 = 2375.8408 -> 2375.84, T − ½μRm = 338.08 − 118.792 = 219.288 -> 219.29
    ≥ T/n = 169.04, H2 = 219.29. Total 537.69."""
    forces = longitudinal().case(C.SAFETY_LR11_B10_REDUCED)
    case = (D("1.1"), False, D("1.23"), D("0.9"), D("0.8"), D("1.23"), D("0.222"), "S10")
    expected_origin = hand_case(case, B_LOADS, None, D("272.47"), None, D(2), D("0.1"), "movable",
                                {"lr": D(400), "b": D(160)})
    expected_end = hand_case((*case[:6], D("0.521"), "S10"), None, D_LOADS, None, D("25.08"), D(2), D("0.1"),
                             "fixed", {"lr": D(200), "b": D(96)})
    assert actual_case(forces.origin) == expected_origin
    assert actual_case(forces.end) == expected_end
    assert expected_origin == (D("636.80"), D("7141.08"), D("318.40"), D("714.11"), D("31.84"), None, D("318.40"))
    assert expected_end == (D("338.08"), D("2375.84"), D("169.04"), None, None, D("219.29"), D("219.29"))
    assert value(forces.total) == D("537.69")


def test_example4_reduced_dead_load_cases_by_hand():
    """Decision 120 on Example橋脚4 (III-45〜57 ③ and ⑤), placing ①, ρf = 1.0; S10 = 0.
    ③ 1.0 LR + 1.1B: end (fixed; far movable): Rm = 0.9 × 4250 + 0.8 × 1050 + 1.0 × 832.29 × 2 = 3825 + 840
    + 1664.58 = 6329.58; T = 1.1 × 382.5 + 500 = 920.75; H2 = 920.75 − 0.05 × 6329.58 = 604.271 -> 604.27
    (> T/n 460.38). Origin: T/n = (1.1 × 142.5 + 160) / 2 = 158.375 -> 158.38 < μRm = 0.1 × (0.9 × 1710
    + 0.8 × 470 + 379.44 × 2) = 0.1 × 2673.88 = 267.388 -> 267.39, so H1 = 158.38. Total 762.65.
    ⑤ 1.1 LR + 1.0B: the end girder's impact i = 0.520 (the double-track girder impact of the input):
    Rm = 3825 + 840 + 832.29 × 2 × 1.520 = 3825 + 840 + 2530.1616 = 7195.1616 -> 7195.16; T = 382.5 + 1.1 × 500
    = 932.5; H2 = 932.5 − 0.05 × 7195.16 = 932.5 − 359.758 = 572.742 -> 572.74 (> T/n 466.25). Origin:
    T/n = (142.5 + 1.1 × 160) / 2 = 159.25 < μRm (> 267), H1 = 159.25. Total 731.99."""
    lon = calculate_reaction(parse_input(load_json(EXAMPLE4_INPUT.read_bytes()))).longitudinal
    braking, rail = lon.case(C.SAFETY_LR10_B11_REDUCED), lon.case(C.SAFETY_LR11_B10_REDUCED)
    assert (braking.origin.bearing, braking.end.bearing) == (BearingType.MOVABLE, BearingType.FIXED)
    assert (value(braking.end.vertical), value(braking.end.applied)) == (D("6329.58"), D("920.75"))
    assert value(braking.end.force) == D("604.27")
    assert (value(braking.origin.friction), value(braking.origin.force)) == (D("267.39"), D("158.38"))
    assert value(braking.total) == D("762.65")
    assert (value(rail.end.vertical), value(rail.end.applied)) == (D("7195.16"), D("932.50"))
    assert value(rail.end.force) == D("572.74")
    assert value(rail.origin.force) == D("159.25")
    assert value(rail.total) == D("731.99")
    # ② (train on the origin girder only) and ③ (end only): the unloaded girder's bearing carries 0.9D1 + 0.8D2
    # (+ S10 = 0): ② fixed end, far D: 0.9 × 4250 + 0.8 × 1050 = 4665.00; ③ movable origin B: 0.9 × 1710
    # + 0.8 × 470 = 1539 + 376 = 1915.00.
    origin_only, end_only = lon.one_girder
    for which in (C.SAFETY_LR10_B11_REDUCED, C.SAFETY_LR11_B10_REDUCED):
        assert value(origin_only.case(which).end.vertical) == D("4665.00")
        assert value(end_only.case(which).origin.vertical) == D("1915.00")


SWAPPED ={"上部構造/支承データ/起点側/支承名": "固定", "上部構造/支承データ/終点側/支承名": "可動",
           "上部構造/支承データ/起点側/摩擦係数_μ": 0.15, "上部構造/支承データ/終点側/摩擦係数_μ": 0.05}


def test_swapped_bearings_by_hand():
    result = longitudinal(pier(**SWAPPED))
    rho, rb, ra, rc, rd = D(1.231), D(272.47), D(367.53), D(294.92), D(25.08)
    b, c = {"d1": D(5740), "d2": D(520), "S2": D(460), "S10": D(740), "S30": D(820)}, \
        {"d1": D(1860), "d2": D(260), "S2": D(250), "S10": D(400), "S30": D(450)}
    a, dd = {"d1": D(5740), "d2": D(660), "S2": D(460), "S10": D(740), "S30": D(820)}, \
        {"d1": D(1860), "d2": D(260), "S2": D(250), "S10": D(400), "S30": D(450)}
    origin = {"lr": D(400), "lr_service": D(320), "b": D(160)}
    end = {"lr": D(200), "lr_service": D(160), "b": D(96)}
    cases = {
        C.SERVICE_LR08: (D(1), True, None, D(1), D(1), None, None, "S2"),
        C.SERVICE_LR10: (D(1), False, None, D(1), D(1), D(1), {"o": D("0.167"), "e": D("0.391")}, "S2"),
        C.SAFETY_LR10_B10: (D(1), False, q(rho, 2), D("1.1"), D("1.2"), q(rho * D("1.1"), 2),
                            {"o": D("0.222"), "e": D("0.521")}, "S10"),
        C.SAFETY_LR10: (D(1), False, None, D("1.1"), D("1.2"), None, None, "S30"),
        C.RESTORABILITY_LR10_B10: (D(1), False, "restore", D(1), D(1), q(rho, 2),
                                   {"o": D("0.222"), "e": D("0.521")}, "S10"),
    }
    for case, (lr, service, brake, d1f, d2f, live, impact, snow) in cases.items():
        origin_brake = q(rho, 2) if brake == "restore" else brake  # no override on the origin side
        end_brake = D(1) if brake == "restore" else brake  # 復旧性制動係数 1.0 on the end side
        expected_origin = hand_case((lr, service, origin_brake, d1f, d2f, live, impact and impact["o"], snow),
                                    b, a, rb, ra, D(2), D("0.15"), "fixed", origin)
        expected_end = hand_case((lr, service, end_brake, d1f, d2f, live, impact and impact["e"], snow),
                                 c, dd, rc, rd, D(2), D("0.05"), "movable", end)
        forces = result.case(case)
        assert actual_case(forces.origin) == expected_origin, case
        assert actual_case(forces.end) == expected_end, case
    assert result.seismic_girder.origin.force.value == 13580.0  # fixed: whole T
    assert result.seismic_girder.end.force.value == 2370.0  # movable: 4740 / 2


def test_movable_floor_uses_the_friction_coefficient():
    # Decision 11: H = min(T/n, max(μ·Rm, μ·T/n)) with μ itself, not 0.1. Light bearings make μ·T/n govern.
    light = {f"{ORIGIN_SLOTS}/{i}/{key}": v for i in range(4)
             for key, v in (("固定死荷重_D1", 10.0), ("付加死荷重_D2", 1.0), ("雪荷重_2年確率", 0.0))}
    result = longitudinal(pier(**light, **{"上部構造/支承データ/起点側/摩擦係数_μ": 0.15}))
    movable = result.case(C.SERVICE_LR08).origin
    assert movable.vertical.value == 44.0  # 40 + 4 + 0
    assert (movable.friction.value, movable.friction_floor.value) == (6.6, 24.0)  # 0.15 × 44, 0.15 × 160
    assert movable.force.value == 24.0  # 0.1 × T/n would give 16.00


def test_recovery_brake_coefficient_absent_uses_rho_times_gamma():
    case = longitudinal(pier(**{"上部構造/支承データ/終点側/復旧性制動係数": None})).case(C.RESTORABILITY_LR10_B10)
    # Example2 7-11 prints T2 = 1.0 × 200.00 + 1.0 × 96.00 = 296.00 (the entered 1.0); without it 1.23 × 96.
    assert case.end.brake_factor.value == 1.23
    assert case.end.applied.value == 318.08


def test_ea17_braking_by_hand():
    """decision 101: braking 25 % of the train load RA + RB on the girder, starting 25 % of its driving axles (the
    170 kN axles of E-17 on the girder, not the line load)."""
    p = pier(**{"上部構造/列車/車両名": "EA-17", "上部構造/列車/編成数": None})
    loading = calculate_reaction(p).train.loading
    result = longitudinal(p)
    for girder, near, far, axles in ((result.origin, loading.rb, loading.ra, loading.origin_axles),
                                     (result.end, loading.rc, loading.rd, loading.end_axles)):
        brake = q(D("0.25") * (D(near.value) + D(far.value)), 2)
        start = q(D("0.25") * D(170) * D(axles.value), 2)
        assert (value(girder.braking), value(girder.starting), value(girder.braking_adopted)) == (
            brake, start, max(brake, start))
        assert value(girder.driving_axles) == D(170) * D(axles.value)
    assert result.origin.braking_rule.value == "EA-17の規定"
    assert longitudinal().origin.driving_axles is None  # P-16 keeps the axle-load formula


def test_axle_rule_braking_by_hand():
    result = longitudinal(pier(**{"上部構造/起点側/桁長/L1": 1.234}))
    length = D("1.234") + D("18.85") + D("0.575")
    assert value(result.origin.length) == length
    brake = q((D("0.20") + D("0.80") / D(20) * length) * D(160), 2)
    start = q((D("0.19") + D("0.76") / D(20) * length) * D(160), 2)
    assert (value(result.origin.braking), value(result.origin.starting)) == (brake, start)
    assert value(result.origin.long_rail) == q(D(10) * length * 2, 2)


def test_long_rail_is_capped_at_2000_kn_per_track():
    result = longitudinal(pier(**{"上部構造/起点側/桁長": {"L1": 1.0, "スパン長": 199.0, "L2": 1.0}}))
    assert result.origin.long_rail.value == 4000.0  # min(10 × 201, 2000) × 2
    assert result.origin.long_rail_service.value == 3216.0  # min(8 × 201, 2000) × 2


def test_track_total_scales_the_long_rail_and_the_train_term():
    shares = {f"{END_SLOTS}/0/列車分担/L2": 0.0, f"{END_SLOTS}/1/列車分担/L2": 0.0}  # 1.000 track on the end side
    result = longitudinal(pier(**shares))
    assert result.end.track_total.value == 1.0
    assert result.end.long_rail.value == 100.0
    fixed = result.case(C.SERVICE_LR10).end
    assert fixed.vertical.value == float(q(D(2370) + D("25.08") * 1 * D("1.391"), 2))


def test_a_girder_without_bearings_on_the_pier():
    result = longitudinal(pier(**{f"{END_SLOTS}/0": None, f"{END_SLOTS}/1": None}))
    assert result.end.track_total.value == 0.0
    assert result.end.long_rail.value == 0.0
    assert result.case(C.SERVICE_LR08).end.applied.value == 0.0


def test_the_braking_and_the_bearing_forces_of_a_train_on_one_girder():
    """Decision 102: ② and ③ have the bearing cases with the train or braking; the girder without the train has no
    braking, and its bearing carries the dead loads only (SERVICE 1.0 LR: D1 + D2 + S2 at the fixed bearing D)."""
    p = pier()
    reaction = calculate_reaction(p)
    lon = reaction.longitudinal
    origin_only, end_only = lon.one_girder
    assert [c.case for c in origin_only.cases] == list(LAYOUT_CASES) == [
        LongitudinalCase.SERVICE_LR10, LongitudinalCase.SAFETY_LR10_B10, LongitudinalCase.SAFETY_LR11_B10,
        LongitudinalCase.SAFETY_LR11_B10_REDUCED,  # decision 120
        LongitudinalCase.SAFETY_LR10_B11, LongitudinalCase.SAFETY_LR10_B11_REDUCED,  # decision 120
        LongitudinalCase.RESTORABILITY_LR10_B10]
    assert (origin_only.end.braking_adopted.value, end_only.origin.braking_adopted.value) == (0.0, 0.0)
    # P-16's braking depends only on the girder length: as ①'s on the loaded girder
    assert origin_only.origin == BrakeForces(lon.origin.braking, lon.origin.starting, lon.origin.braking_adopted)
    far = reaction.dead.end.far
    bearing = origin_only.case(LongitudinalCase.SERVICE_LR10).end
    assert bearing.bearing is BearingType.FIXED
    assert value(bearing.vertical) == D(far.d1.value) + D(far.d2.value) + D(far.snow2.value)
