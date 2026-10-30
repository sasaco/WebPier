"""The horizontal forces along the track at the bearings on the cantilever (decision 125, CONTEXT.md 片持ち梁の支承の
水平荷重; Example橋脚4 V-13〜V-25): T of each girder from 0600 with the braking of the loading's train layout, T / n per
bearing, capped by μ·Ni at a movable girder end, Mt = Hi × Y.

The expected values are hand calculations from the inputs (current.json, Example2's girders; the Example橋脚4 input)
and from 0600's T, whose own tests fix it. The sample's numbers differ where 0600 or its per-bearing loads do; the
comparison is test_example4_against_the_sample."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cantilever_support import D, pier, q, reaction_of, result_of, value
from webpier.calc.cantilever import Side
from webpier.calc.cantilever.actions import ActionKey
from webpier.calc.cantilever.bearings import (LAYOUTS, SEISMIC, BearingCase, GirderForce, bearing_case, girder_force,
                                              label, seismic_force)
from webpier.calc.cantilever.combinations import DEFINITIONS
from webpier.calc.cantilever.loads import Loading
from webpier.calc.moving_load import Girder
from webpier.calc.reaction.longitudinal import BearingType, LongitudinalCase
from webpier.calc.reaction.train import Layout
from webpier.core.printed import FORCE, LENGTH
from webpier.inputs import parse_input

ROOT = Path(__file__).parents[2]
EXAMPLE4 = json.loads((ROOT / ".claude" / "docs" / "Example橋脚4" / "pre" / "input.json").read_text(encoding="utf-8"))
SAMPLE4 = json.loads((ROOT / "tests" / "fixtures" / "example4" / "cantilever_responses.json").read_text(encoding="utf-8"))
NUMBERS = (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 24, 25, 26, 28)  # the cases with bearing forces along the track


@pytest.fixture(scope="module")
def current():
    return result_of()


def _case(result, number: int, side: Side = Side.LEFT) -> BearingCase:
    return next(case for case in result.sides[side].bearings if case.number == number)


def test_every_case_with_a_longitudinal_bearing_force_has_its_bearing_case_in_case_order(current):
    _, _, result = current
    for side in Side:
        found = result.sides[side].bearings
        assert [case.number for case in found] == list(NUMBERS)
        assert [case.combination for case in found] == [DEFINITIONS[n - 1].bearing for n in NUMBERS]
        assert [case.loading for case in found] == [*Loading] * 3 + [None] + [*Loading] + [None]
        assert found[-1].label == SEISMIC and found[-1].combination is None
        assert [case.label for case in found[:10]] == ["1.0 LR + 1.23B"] * 3 + ["1.0 LR + 1.35B"] * 3 + [
            "1.1 LR + 1.23B"] * 3 + ["1.0 LR"]
    assert LAYOUTS == {Loading.ORIGIN_MAX: Layout.ORIGIN, Loading.END_MAX: Layout.END, Loading.BOTH_MAX: Layout.BOTH}


def test_t_takes_the_braking_of_the_train_layout_of_the_loading(current):
    """0600's T = LR + 1.23 × B of the layout: ① both girders (B 160.00 and 96.00), ② the origin girder only (the
    end girder brakes nothing: LR 200.00 alone), ③ the end girder only (the origin girder LR 400.00 alone)."""
    _, reaction, result = current
    longitudinal = reaction.longitudinal
    case_9, case_10, case_11 = (_case(result, n) for n in (9, 10, 11))  # B支点最大, C支点最大, B+C支点最大
    assert (case_11.origin.applied.value, case_11.end.applied.value) == (596.8, 318.08)  # 400 + 1.23 × 160, 200 + 1.23 × 96
    assert value(case_11.origin.applied) == D(400) + q(D("1.23") * D(160), 2)
    assert (case_9.origin.applied.value, case_9.end.applied.value) == (596.8, 200.0)
    assert (case_10.origin.applied.value, case_10.end.applied.value) == (400.0, 318.08)
    origin_only = next(item for item in longitudinal.one_girder if item.layout is Layout.ORIGIN)
    assert case_9.end.applied == origin_only.case(LongitudinalCase.SAFETY_LR10_B10).end.applied
    assert case_11.origin.applied == longitudinal.case(LongitudinalCase.SAFETY_LR10_B10).origin.applied
    # 1.1 LR + 1.23B, C支点最大: 1.1 × 400 = 440.00 (the origin girder without braking), 1.1 × 200 + 1.23 × 96 = 338.08
    case_16 = _case(result, 16)
    assert (case_16.origin.applied.value, case_16.end.applied.value) == (440.0, 338.08)
    # 1.0 LR (雪最大, no train): ①'s LR alone
    case_18 = _case(result, 18)
    assert case_18.loading is None and (case_18.origin.applied.value, case_18.end.applied.value) == (400.0, 200.0)


def test_t_keeps_its_terms_as_the_report_prints_them(current):
    """T = γB × B + the LR factor × LR (no braking term for a girder without the layout's train or a case without
    braking), and in the seismic case Kh × the girder's dead load + the seismic train; the terms sum to T."""
    _, reaction, result = current
    longitudinal = reaction.longitudinal

    def terms(force: GirderForce) -> list[tuple[float | None, float]]:
        return [(None if by is None else by.value, item.value) for by, item in force.terms]

    case_9 = _case(result, 9)
    assert terms(case_9.origin) == [(1.23, 160.0), (1.0, 400.0)]
    assert [by.digits for by, _ in case_9.origin.terms] == [2, 1]  # 1.0 LR, as 0600 writes it
    assert terms(case_9.end) == [(1.0, 200.0)]  # ② has no train on the end girder
    assert terms(_case(result, 16).origin) == [(1.1, 400.0)]
    assert terms(_case(result, 18).origin) == [(1.0, 400.0)]  # 1.0 LR: no braking factor
    seismic = _case(result, 28)
    assert terms(seismic.origin) == [(0.386, longitudinal.origin.seismic_girder.value),
                                     (None, longitudinal.origin.seismic_train.value)]
    for case in result.sides[Side.LEFT].bearings:
        for force in (case.origin, case.end):
            assert value(force.applied) == q(sum(value(item) * (1 if by is None else value(by))
                                                  for by, item in force.terms), 2)


def test_n_is_the_occupied_bearing_slots_of_the_girder_and_each_bearing_takes_t_over_n(current):
    _, _, result = current
    case = _case(result, 11)
    origin, end = case.origin, case.end
    assert (origin.girder, origin.bearing, origin.count) == (Girder.ORIGIN, BearingType.MOVABLE, 4)
    assert (end.girder, end.bearing, end.count) == (Girder.END, BearingType.FIXED, 2)
    assert value(origin.share) == q(D("596.8") / 4, 2) == D("149.20")
    assert value(end.share) == q(D("318.08") / 2, 2) == D("159.04")
    assert origin.inertia is None and end.inertia is None


def test_a_movable_bearing_is_capped_by_mu_times_its_own_vertical_force_of_the_case(current):
    """Case 9 (1.1D1 + 1.2D2 + S10 + 1.35(L + I), B支点最大), the origin girder's G1 on the left cantilever:
    Ni = 1.1 × 1530 + 1.2 × 160 + 320 + 1.35 × 250.77 + 1.35 × 61.44 = 2616.4835 → 2616.48 (the train of B支点最大 with
    RB 532.41, decision 125), μ·Ni = 261.648 → 261.65, T / n = 149.20 < 261.65: Hi = 149.20, Mt = 149.20 × 1.350 =
    201.42."""
    _, _, result = current
    origin, end = _case(result, 9).bearings
    assert origin.bearing.label == "起点側 Ｇ1桁" and end.bearing.label == "終点側 Ｇ1桁"
    ni = D("1.1") * D(1530) + D("1.2") * D(160) + D(320) + D("1.35") * D("250.77") + D("1.35") * D("61.44")
    assert value(origin.vertical) == q(ni, 2) == D("2616.48")
    assert value(origin.cap) == q(D("0.1") * D("2616.48"), 2)
    assert value(origin.force) == D("149.20") and origin.share.value == 149.2
    assert value(origin.moment) == q(D("149.20") * D("1.35"), 2) and origin.arm.value == 1.35
    # the fixed end: T / n = 200.00 / 2 = 100.00, no cap
    assert (end.vertical, end.cap, end.force.value, end.moment.value) == (None, None, 100.0, 135.0)
    # 使用性（損傷） case 24 (D1 + D2 + S10 + 1.23(L + I), B支点最大): the same T, its own Ni
    serviceability = _case(result, 24).bearings[0]
    ni = D(1530) + D(160) + D(320) + D("1.23") * (D("250.77") + D("61.44"))
    assert value(serviceability.vertical) == q(ni, 2) == D("2394.02")
    assert serviceability.force == origin.force
    # 1.0 LR + 1.35B (case 12: the train without impact) and 1.1 LR + 1.23B (case 15: no snow)
    ni_12 = D("1.1") * D(1530) + D("1.2") * D(160) + D(320) + D("1.23") * D("250.77")
    assert value(_case(result, 12).bearings[0].vertical) == q(ni_12, 2)
    ni_15 = D("1.1") * D(1530) + D("1.2") * D(160) + D("1.23") * (D("250.77") + D("61.44"))
    assert value(_case(result, 15).bearings[0].vertical) == q(ni_15, 2)
    # 雪最大 (case 18): 1.1 × 1530 + 1.2 × 160 + 360 = 2235.00
    assert value(_case(result, 18).bearings[0].vertical) == D("2235.00")


def test_a_smaller_mu_caps_the_movable_bearing():
    """μ = 0.05: case 9's cap 0.05 × 2616.48 = 130.824 → 130.82 < 149.20, case 24's 0.05 × 2394.02 = 119.701 →
    119.70; Mt = 130.82 × 1.350 = 176.607 → 176.61. The fixed end girder is not capped."""
    _, _, result = result_of(**{"上部構造/支承データ/起点側/摩擦係数_μ": 0.05})
    origin, end = _case(result, 9).bearings
    assert value(origin.cap) == D("130.82") and origin.force == origin.cap and origin.share.value == 149.2
    assert value(origin.moment) == q(D("130.82") * D("1.35"), 2) == D("176.61")
    assert value(_case(result, 24).bearings[0].force) == D("119.70")
    assert end.cap is None and end.force.value == 100.0
    assert value(_case(result, 9).force) == D("130.82") + D("100.00")
    assert value(_case(result, 9).moment) == q(D("130.82") * D("1.35"), 2) + D("135.00")


def test_the_seismic_case_takes_kh_times_the_girder_inertia_and_caps_the_movable_end(current):
    """T1 = 0.386 × 13580.00 + 128.00 = 5369.88, / 4 = 1342.47; Ni = 1530 + 160 + 200 (S2) + 150.72 = 2040.72,
    μ·Ni = 204.072 → 204.07 < 1342.47: Hi = 204.07, Mt = 204.07 × 1.350 = 275.4945 → 275.49.
    T2 = 0.386 × 4740.00 + 64.00 = 1893.64 at the fixed end, / 2 = 946.82, Mt = 1278.207 → 1278.21."""
    _, reaction, result = current
    case = _case(result, 28)
    assert case.combination is None and case.loading is None and case.label == SEISMIC
    assert value(case.origin.inertia) == q(D("0.386") * D(13580), 2) and case.origin.applied.value == 5369.88
    assert value(case.end.inertia) == q(D("0.386") * D(4740), 2) and case.end.applied.value == 1893.64
    assert case.origin.applied == seismic_force(pier(), reaction.longitudinal, result.basis.girders, Girder.ORIGIN,
                                                result.longitudinal.kh).applied
    origin, end = case.bearings
    assert value(origin.share) == q(D("5369.88") / 4, 2)
    assert value(origin.vertical) == D(1530) + D(160) + D(200) + D("150.72")
    assert value(origin.cap) == D("204.07") and origin.force == origin.cap
    assert value(origin.moment) == D("275.49")
    assert (end.cap, value(end.force), value(end.moment)) == (None, D("946.82"), D("1278.21"))
    assert (case.force.value, case.moment.value) == (1150.89, 1553.7)


def test_a_fixed_origin_and_a_movable_end_swap_the_roles():
    """The movable end girder's G1 in case 11 (B+C支点最大): Ni = 1.1 × 930 + 1.2 × 130 + 200 + 1.35 × (294.92 +
    153.65) = 1023 + 156 + 200 + 605.5695 = 1984.5695 → 1984.57, μ·Ni = 198.46 > T / n = 159.04."""
    _, _, result = result_of(**{"上部構造/支承データ/起点側/支承名": "固定", "上部構造/支承データ/終点側/支承名": "可動",
                                "上部構造/支承データ/終点側/復旧性制動係数": None})
    case = _case(result, 11)
    origin, end = case.bearings
    assert case.origin.bearing is BearingType.FIXED and case.end.bearing is BearingType.MOVABLE
    assert origin.cap is None and origin.force == origin.share
    ni = D("1.1") * D(930) + D("1.2") * D(130) + D(200) + D("1.35") * (D("294.92") + D("153.65"))
    assert value(end.vertical) == q(ni, 2) and value(end.cap) == D("198.46") and end.force.value == 159.04
    seismic = _case(result, 28)
    assert seismic.bearings[0].cap is None and seismic.bearings[1].cap is not None


def test_a_girder_without_a_bearing_has_no_share():
    pier_input = pier()
    reaction = reaction_of(pier_input)
    girders = {**result_of(pier_input)[2].basis.girders}
    girders[Girder.END] = type(girders[Girder.END])(Girder.END, (), LENGTH(0))
    force = girder_force(pier_input, reaction.longitudinal, girders, Girder.END, LongitudinalCase.SAFETY_LR10_B10,
                         Loading.BOTH_MAX)
    assert (force.count, force.share, force.applied.value) == (0, None, 318.08)
    # the cantilever carries none of its bearings, so the case needs no share of it
    geometry = result_of(pier_input)[2].basis.sides[Side.LEFT]
    origin_only = type(geometry)(geometry.side, geometry.overhang, geometry.half_column, geometry.torsion_arm,
                                 geometry.girders, geometry.bearings[:1], geometry.self_weight)
    origin = girder_force(pier_input, reaction.longitudinal, girders, Girder.ORIGIN, LongitudinalCase.SAFETY_LR10_B10,
                          Loading.BOTH_MAX)
    found = bearing_case(pier_input, 11, LongitudinalCase.SAFETY_LR10_B10, Loading.BOTH_MAX, "x",
                         {Girder.ORIGIN: origin, Girder.END: force}, origin_only, lambda bearing: FORCE(1000))
    assert [item.force.value for item in found.bearings] == [100.0]  # min(149.20, 0.1 × 1000)
    assert isinstance(found.end, GirderForce)


def test_the_bearing_actions_list_each_bearing_on_the_cantilever(current):
    _, _, result = current
    tables = {action.key: action for action in result.sides[Side.LEFT].actions}
    action = tables[ActionKey.bearing(9)]
    assert action.title == "1.0 LR + 1.23B B支点最大の支承に働く水平荷重"
    assert [(row.label, row.sublabel, row.h.value, row.arm.value, row.mt.value) for row in action.rows] == [
        ("起点側", "Ｇ1桁", 149.2, 1.35, 201.42), ("終点側", "Ｇ1桁", 100.0, 1.35, 135.0)]
    assert (action.h.value, action.mt.value, action.n.value, action.md.value) == (249.2, 336.42, 0.0, 0.0)
    assert tables[ActionKey.bearing(18)].title == "1.0 LRの支承に働く水平荷重"
    assert tables[ActionKey.bearing(28)].title == "地震時線路方向"
    assert ActionKey.bearing(28) == ActionKey("LRB", "28")
    assert label(LongitudinalCase.SAFETY_LR10, reaction_of(pier()).longitudinal) == "1.0 LR"


# --- Example橋脚4 (V-13〜V-25): R5's rule on the sample's input ------------------------------------------------------


@pytest.fixture(scope="module")
def example4():
    return result_of(parse_input(EXAMPLE4), longitudinal=0.495, transverse=0.786)


def test_example4_hand_calculations(example4):
    """The movable origin girder (μ 0.1, n = 2) and the fixed end girder (n = 4) of the Example橋脚4 input; per bearing
    D1 855.0 / 1062.5, D2 235.0 / 262.5, no snow, ρ = 1.0, Y = (1.50 + 0.50)/2 = 1.000.

    Case 11 (B+C支点最大, 1.1D1 + 1.2D2 + 1.10(L + I)): T1 = 160.00 + 142.50 = 302.50 (0600), / 2 = 151.25;
    N = 1.1 × 855 + 1.2 × 235 + 1.10 × (379.44 + 198.07) = 1857.761 → 1857.76, μN = 185.78 > 151.25: 151.25.
    T2 = 500.00 + 382.50 = 882.50, / 4 = 220.625 → 220.63 (fixed).
    Seismic (Kh 0.495): T1 = 0.495 × 4360.00 + 56.00 = 2158.20 + 56.00 = 2214.20, / 2 = 1107.10;
    N = 855 + 235 + 130.48 = 1220.48, μN = 122.048 → 122.05 < 1107.10: 122.05.
    T2 = 0.495 × 10600.00 + 175.00 = 5422.00, / 4 = 1355.50 (fixed, no cap)."""
    _, _, result = example4
    case = _case(result, 11)
    origin, end = case.bearings
    assert origin.bearing.label == "起点側 Ｇ1桁" and end.bearing.label == "終点側 Ｇ1桁"
    assert (case.origin.count, case.end.count, origin.arm.value) == (2, 4, 1.0)
    assert (case.origin.applied.value, value(origin.share)) == (302.5, D("151.25"))
    n = D("1.1") * D(855) + D("1.2") * D(235) + D("1.10") * (D("379.44") + D("198.07"))
    assert value(origin.vertical) == q(n, 2) == D("1857.76") and value(origin.cap) == D("185.78")
    assert origin.force == origin.share
    assert (case.end.applied.value, value(end.force), end.cap) == (882.5, D("220.63"), None)
    seismic = _case(result, 28)
    origin, end = seismic.bearings
    assert value(seismic.origin.applied) == q(D("0.495") * D(4360), 2) + D(56) == D("2214.20")
    assert value(origin.share) == D("1107.10")
    assert value(origin.vertical) == D(855) + D(235) + D("130.48") and value(origin.cap) == D("122.05")
    assert origin.force == origin.cap
    assert value(seismic.end.applied) == q(D("0.495") * D(10600), 2) + D(175) == D("5422.00")
    assert value(end.force) == q(D("5422.00") / 4, 2) == D("1355.50") and end.cap is None


def test_example4_against_the_sample(example4):
    """Where WebPier's T agrees with the sample (V-25 seismic T, the end girder's 1355.5) and where it does not:
    0600's braking is one track's (0.25 × the girder's train, reaction_notes 7: B(起) 142.50 / 127.50 / 0, B(終) 382.50
    / 0 / 425.00) where the sample takes both tracks' 255.0 / 340.0 and 765.0 / 850.0 (owner decision, 問11), and the
    per-bearing train of 0900 is 0600's with its line load (379.44 for the sample's 368.3). The sample's cap adds the
    girder end's 1710.0 to one bearing's train (decision 125: (見本)); WebPier's is per bearing."""
    _, _, result = example4
    longitudinal = SAMPLE4["longitudinal"]
    seismic = longitudinal["seismic"]
    case = _case(result, 28)
    assert case.origin.applied.value == float(seismic["start"]["T"]) == 2214.2
    assert case.end.applied.value == float(seismic["end"]["T"]) == 5422.0
    assert case.bearings[1].force.value == float(seismic["end"]["per_stopper"]) == 1355.5
    assert value(case.origin.share) == D(seismic["start"]["Ts"])  # 1107.1
    assert case.bearings[0].force.value == 122.05 != float(seismic["start"]["adopted"]["T1"])  # the sample 231.1
    # LR agrees (160.0 and 500.0), B does not
    by_case = {item["case"]: item for item in longitudinal["cases"]}
    assert _case(result, 11).origin.applied.value == 302.5 != float(by_case["①-1"]["start"]["T"])  # 415.0
    assert _case(result, 9).end.applied.value == 500.0 == float(by_case["①-2"]["end"]["T"])  # LR alone
    assert _case(result, 10).origin.applied.value == 160.0 == float(by_case["①-3"]["start"]["T"])  # LR alone
