"""0600 longitudinal forces on the girders and bearings: Example2 07 7-4 to 7-13 and hand calculations."""

from decimal import Decimal

import pytest

from reaction_support import D, END_SLOTS, ORIGIN_SLOTS, example2, pier, q, value
from webpier.calc.reaction import calculate_reaction
from webpier.calc.reaction.longitudinal import BearingType, LongitudinalCase

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
    # 7-8, 7-9: 7678 + 1.23 × 272.47 × 2 × 1.222 = 8497.07752 -> 8497.08 (Example2 8497.07 from RB 272.4668)
    ("bearing.safety.1_1LR_1_23B", "movable"): 8497.08,
    ("bearing.safety.1_0LR_1_35B", "movable"): 8497.08,
    # 7-11: 7000 + 1.23 × 272.47 × 2 × 1.222 = 7819.07752 -> 7819.08 (Example2 7819.07 from RB 272.4668)
    ("bearing.restorability.1_0LR_1_23B", "movable"): 7819.08,
    # 7-6: 2370 + 25.08 × 2 × (1 + 0.391) = 2439.77256 -> 2439.77 (Example2 2439.78 from RD 25.0811)
    ("bearing.serviceability_crack_need.1_0LR", "fixed"): 2439.77,
    # 7-8, 7-9: 2758 + 1.23 × 25.08 × 2 × 1.521 = 2851.84083 -> 2851.84. Example2 prints 2851.85, which the
    # unrounded RD does not give either (2851.8449); not reproducible from the page.
    ("bearing.safety.1_1LR_1_23B", "fixed"): 2851.84,
    ("bearing.safety.1_0LR_1_35B", "fixed"): 2851.84,
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


@pytest.mark.parametrize("case", list(PREFIX), ids=lambda case: case.name)
def test_example2_bearing_cases_7_5_to_7_12(case):
    prefix, summary = PREFIX[case]
    forces = longitudinal().case(case)
    movable, fixed = forces.origin, forces.end
    assert (movable.bearing, fixed.bearing) == (BearingType.MOVABLE, BearingType.FIXED)
    assert movable.applied.value == EX[f"{prefix}.T1"]
    assert fixed.applied.value == EX[f"{prefix}.T2"]
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


SWAPPED = {"上部構造/支承データ/起点側/支承名": "固定", "上部構造/支承データ/終点側/支承名": "可動",
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
    result = longitudinal(pier(**{"上部構造/列車/車両名": "EA-17"}))
    # EA-17: braking (0.27 + 1.00/Lv) ΣR, starting (0.25 + 0.95/Lv) ΣR, ΣR = RA + RB of the girder.
    for girder, total in ((result.origin, D(367.53) + D(272.47)), (result.end, D(294.92) + D(25.08))):
        brake = q((D("0.27") + D("1.00") / D(20)) * total, 2)
        start = q((D("0.25") + D("0.95") / D(20)) * total, 2)
        assert (value(girder.braking), value(girder.starting), value(girder.braking_adopted)) == (
            brake, start, max(brake, start))
    assert result.origin.braking.value == 204.8  # 0.32 × 640


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
