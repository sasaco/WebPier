"""0620 FrameWeb load cases: Example2 09 pp.9-3 to 9-13 and its FrameWeb file.

Signs as in 0610: tx = H, ty = −N, rz = −M; a zero component is null. Member loads are global: gy = −n of the
column line load, gx = h of the wind on the pier body. A partial or varying member load is one row per member:
L1 from the member start (the upper node on the column line, the base of a pedestal), L2 the unloaded margin
before the member end, P1 at the load start and P2 at its end (validate.py).
"""

from dataclasses import replace

import pytest

from frameweb_support import (
    CURVE, EXAMPLE2_09, EXAMPLE2_GROUND, T09, T_ASYMMETRIC, T_PEDESTAL, WIDTHS, ground, transverse,
)
from webpier.calc.frame import NodeRole
from webpier.calc.load_nature import Nature, SpringTerm, spring_term
from webpier.calc.transverse import BasicCase, Define
from webpier.calc.transverse.wind import MemberLoad
from webpier.core.printed import LENGTH, LINE_LOAD
from webpier.export.frameweb import build_frameweb_transverse
from webpier.export.frameweb.build import frameweb_document
from webpier.export.frameweb.cases import Cases, LoadCase

B = BasicCase
# Example2 prints these from unrounded intermediates; the calc uses the printed operands (tests/calc
# test_transverse_loads): 9-5 567.39 / ±1210.08 -> 567.38 / ±1210.09, 1134.77 -> 1134.78; 9-6 227.78 / ±483.45
# -> 227.77 / ±483.47. Case 15: Example2 saves H −111.69 with rz −430.01, a moment of the other direction; the
# calc's H +111.69 at 3.850 above the seat gives M = +430.01 (rz −430.01), and Define 13 takes both signs anyway.
# Cases 16 and 17: the M of the girder wind is the calc's (tests/calc test_transverse_horizontal: the shelter is
# folded into h4, 2124.50 / 4248.93 for Example2's 1001.33 / 2002.64); the pier wind is in load_member.
DIFFERENT = {"9": [("1", None, -567.38, -1210.09)], "10": [("1", None, -567.38, 1210.09)],
             "11": [("1", None, -1134.78, None)], "12": [("1", None, -227.77, -483.47)],
             "13": [("1", None, -227.77, 483.47)], "15": [("1", 111.69, None, -430.01)],
             "16": [("1", 305.88, None, -2124.5)], "17": [("1", 611.75, None, -4248.93)]}
# The nature of each basic case (Example2 9-13 names), for the spring rule of decision 36.
NATURES = {B.D1: Nature.DEAD, B.D2: Nature.DEAD, B.BUOYANCY_HIGH: Nature.WATER, B.BUOYANCY_NORMAL: Nature.WATER,
           B.BUOYANCY_LOW: Nature.WATER, B.SNOW2: Nature.SNOW, B.SNOW10: Nature.SNOW, B.SNOW30: Nature.SNOW,
           B.TRAIN_UP: Nature.TRAIN, B.TRAIN_DOWN: Nature.TRAIN, B.TRAIN_DOUBLE: Nature.TRAIN,
           B.IMPACT_UP: Nature.IMPACT, B.IMPACT_DOWN: Nature.IMPACT, B.IMPACT_DOUBLE: Nature.IMPACT,
           B.LATERAL: Nature.LATERAL, B.WIND_WITH_TRAIN: Nature.WIND, B.WIND_WITHOUT_TRAIN: Nature.WIND,
           B.CENTRIFUGAL_UP: Nature.CENTRIFUGAL, B.CENTRIFUGAL_DOWN: Nature.CENTRIFUGAL,
           B.CENTRIFUGAL_DOUBLE: Nature.CENTRIFUGAL}
SPRING_SETS = {SpringTerm.LONG: 1, SpringTerm.SHORT: 2}


@pytest.fixture(scope="module")
def result():
    return transverse()


@pytest.fixture(scope="module")
def current(result):
    return build_frameweb_transverse(result)


def node_rows(case):
    return [(row["n"], row["tx"], row["ty"], row["rz"]) for row in case.get("load_node", [])]


def member_rows(case):
    return [(row["m1"], row["direction"], row["L1"], row["L2"], row["P1"], row["P2"])
            for row in case.get("load_member", [])]


def test_basic_load_cases_are_those_of_example2(current):
    for number in map(str, range(1, 18)):
        assert node_rows(current["load"][number]) == DIFFERENT.get(number, node_rows(EXAMPLE2_09["load"][number]))


def test_load_case_headers(current):
    # fix_node is the 9-13 spring set (the same in the Example2 file); symbols are those of the Example2 file.
    printed = {row["no"]: row["spring"] for row in T09["basic_cases"]["rows"]}
    for number in range(1, 18):
        case, example = current["load"][str(number)], EXAMPLE2_09["load"][str(number)]
        assert list(case)[:6] == ["fix_node", "element", "symbol", "LL_pitch", "rate", "name"]
        assert case["fix_node"] == printed[number] == example["fix_node"]
        assert (case["element"], case["LL_pitch"], case["rate"]) == (1, 0.1, 1)
        assert case["symbol"] == example["symbol"]
        # Example2 writes a half-width space before 上り in case 12 only.
        assert case["name"] == {12: "衝撃荷重　安全性・復旧性　単線　上り"}.get(number, example["name"])


@pytest.mark.parametrize("changes", [{}, CURVE], ids=["straight", "curve"])
def test_spring_sets_follow_the_nature_of_the_loads(changes):
    # Decision 36: dead loads, buoyancy and snow long-term (1); train, impact, lateral, wind and centrifugal
    # short-term (2). The serviceability impacts are impacts too.
    result = transverse(**changes)
    document = build_frameweb_transverse(result)
    for number, action in enumerate(result.basic_cases, 1):
        assert document["load"][str(number)]["fix_node"] == SPRING_SETS[spring_term(frozenset({NATURES[action.case]}))]
    service = [n for n, case in document["load"].items() if case["symbol"].endswith("s")]
    assert service and all(document["load"][n]["fix_node"] == SPRING_SETS[spring_term(frozenset({Nature.IMPACT}))]
                           for n in service)


def test_the_column_line_load_is_one_row_per_member(current):
    (example, _empty) = EXAMPLE2_09["load"]["1"]["load_member"]
    assert (example["m1"], example["m2"], example["direction"], example["P1"]) == ("1", "3", "x", 297.68)
    assert member_rows(current["load"]["1"]) == [(str(m), "gy", 0, 0, -297.68, -297.68) for m in (1, 2, 3)]


def test_the_wind_on_the_pier_is_that_of_example2_with_its_ground():
    # Example2 9-12 loads Hw1 from node 1 down to 1.080 above node 4 (the ground, Df − H6), as one range row
    # "1" to "-3" with L2 1.08 in the local y of the members (+x for these members running down). The same load is
    # three rows: members 1 and 2 whole, member 3 (4.900) with the margin 1.080 above node 4. Example2 takes the
    # column width 2.70 for the whole pier; here B1 = B6 = 2.700, so 1.5 × 2.700 = 4.05 and 3.0 × 2.700 = 8.10.
    document = build_frameweb_transverse(transverse(**EXAMPLE2_GROUND))
    for number in ("16", "17"):
        example, _empty = (EXAMPLE2_09["load"][number]["load_member"] + [None])[:2]
        assert (example["m1"], example["m2"], example["L1"], example["L2"]) == ("1", "-3", "0", 1.08)
        p = example["P1"]
        assert member_rows(document["load"][number]) == [("1", "gx", 0, 0, p, p), ("2", "gx", 0, 0, p, p),
                                                         ("3", "gx", 0, 1.08, p, p)]


def test_the_wind_stops_at_the_ground(current):
    # current.json: df = 2.000, the ground 4.700; member 3 (7.600 -> 2.700) is loaded over 2.900 from its top.
    assert member_rows(current["load"]["16"]) == [("1", "gx", 0, 0, 4.05, 4.05), ("2", "gx", 0, 0, 4.05, 4.05),
                                                  ("3", "gx", 0, 2, 4.05, 4.05)]
    assert [n for n, case in current["load"].items() if "load_member" in case] == ["1", "16", "17"]


def test_the_haunch_takes_a_trapezoid():
    # Decision 12: beam B1 = 3.200, haunch 3.200 -> 2.900, column B6 = 2.500 (1.5 × each width).
    document = build_frameweb_transverse(transverse(**WIDTHS))
    assert member_rows(document["load"]["16"]) == [("1", "gx", 0, 0, 4.8, 4.8), ("2", "gx", 0, 0, 4.8, 4.35),
                                                   ("3", "gx", 0, 2, 3.75, 3.75)]


def test_the_ground_inside_the_haunch_cuts_the_trapezoid():
    # Ground 7.900, 0.300 above the haunch bottom: loaded 0.400 from its top, the width there 3.029 (calc), so
    # 3.0 × 3.029 = 9.09 at the end of the load and a margin 0.700 − 0.400 = 0.300. The column is not loaded.
    result = transverse(**WIDTHS, **ground(5.2))
    document = build_frameweb_transverse(result)
    assert member_rows(document["load"]["17"]) == [("1", "gx", 0, 0, 9.6, 9.6), ("2", "gx", 0, 0.3, 9.6, 9.09)]


def test_no_pier_wind_with_the_ground_above_the_pier():
    document = build_frameweb_transverse(transverse(**ground(8.0)))
    assert [n for n, case in document["load"].items() if "load_member" in case] == ["1"]
    assert node_rows(document["load"]["16"]) == [("1", 305.88, None, -2124.5)]


def test_pedestal_loads_act_at_the_pedestal_top():
    # Decision 29: the bearing loads at the pedestal top (node 8), the pier parts at the beam top (node 1), with
    # M moved to the seat as M − N × (−0.500). Decision 35: the pedestal (member 7, from its base) takes the wind
    # over B3 = 1.000.
    result = transverse(**T_PEDESTAL)
    document = build_frameweb_transverse(result)
    seat = str(result.frame.node(NodeRole.PEDESTAL_TOP).number)
    assert node_rows(document["load"]["1"]) == [(seat, None, -7600, -3800), ("1", None, -750.98, 25.73),
                                                ("5", None, -4167.45, None)]
    assert node_rows(document["load"]["9"]) == [(seat, None, -567.38, -1493.78)]
    assert node_rows(document["load"]["15"]) == [(seat, 111.69, None, -430.01)]
    assert member_rows(document["load"]["16"])[0] == ("7", "gx", 0, 0, 1.5, 1.5)
    assert [r[0] for r in member_rows(document["load"]["16"])] == ["7", "1", "2", "3"]
    assert [r[0] for r in member_rows(document["load"]["1"])] == ["1", "2", "3"]  # not on the pedestal


def test_the_ground_inside_the_pedestal_loads_its_top():
    # Ground 10.450: the pedestal (10.300 -> 10.600) is loaded from 0.150 above its base to its top.
    document = build_frameweb_transverse(transverse(**T_PEDESTAL, **ground(7.75)))
    assert member_rows(document["load"]["16"]) == [("7", "gx", 0.15, 0, 1.5, 1.5)]


def test_asymmetric_footing_loads_keep_their_levers():
    result = transverse(**T_ASYMMETRIC)
    document = build_frameweb_transverse(result)
    footing = result.fixed.footing
    assert footing.m.value != 0
    assert node_rows(document["load"]["1"])[1] == ("5", None, -footing.n.value, -footing.m.value)


def expected_rows(action, frame):
    lengths = {m.number: m.height.value for m in frame.members}
    lines = [(str(m), "gy", 0, 0, -line.n.value, -line.n.value) for line in action.line_loads for m in line.members]
    partial = [(str(load.member), "gx", load.start.value, round(lengths[load.member] - load.end.value, 3),
                load.h_start.value, load.h_end.value) for load in action.member_loads]
    return lines + partial


@pytest.mark.parametrize("changes", [{}, T_PEDESTAL, WIDTHS | ground(5.2), T_ASYMMETRIC],
                         ids=["current", "pedestal", "haunch_cut", "asymmetric"])
def test_every_load_is_the_printed_action(changes):
    # Values are copied from the calc result: no rounding, no scaling. After the basic cases come the
    # serviceability impacts (up, down, double) of combinations 5, 7, 15 and 16.
    result = transverse(**changes)
    document = build_frameweb_transverse(result)
    service = {c.define: c for c in result.combinations[14].components + result.combinations[4].components}
    auxiliary = [a.source for define in (Define.IMPACT_SINGLE, Define.IMPACT_DOUBLE)
                 for a in service[define].alternatives]
    actions = [*result.basic_cases, *auxiliary]
    assert list(document["load"]) == [str(n) for n in range(1, len(actions) + 1)] and len(actions) == 20
    for number, action in enumerate(actions, 1):
        case = document["load"][str(number)]
        expected = [(str(p.node), p.h.value or None, -p.n.value or None, -p.m.value or None)
                    for p in action.points if (p.n.value, p.h.value, p.m.value) != (0, 0, 0)]
        assert node_rows(case) == expected
        assert member_rows(case) == expected_rows(action, result.frame)


def one_case(member_loads):
    load = LoadCase(symbol="W", name="", spring=2, points=(), line_loads=(), member_loads=member_loads)
    return Cases(loads=(load,), defines=((1,),), combines=(), pickups=())


def test_a_zero_member_load_has_no_row(result):
    zero = MemberLoad(1, LENGTH(0), LENGTH(1), LINE_LOAD(0), LINE_LOAD(0))
    document = frameweb_document(result.frame, one_case((zero,)))
    assert "load_member" not in document["load"]["1"]


def test_a_partial_load_on_an_inclined_member_is_refused():
    # The margin before the end of an inclined member is not a printed number: it cannot be written exactly.
    result = transverse(**T_ASYMMETRIC)
    inclined = result.frame.members[3]
    assert inclined.height.value and inclined.offset.value
    load = MemberLoad(inclined.number, LENGTH(0), LENGTH(1), LINE_LOAD(1), LINE_LOAD(1))
    with pytest.raises(ValueError, match="member 4"):
        frameweb_document(result.frame, one_case((load,)))


def test_a_load_on_a_horizontal_member_measures_its_margin_along_x():
    result = transverse(**T_PEDESTAL)
    arm = result.frame.members[5]  # beam top to the pedestal base, 0.500 long
    assert (arm.height.value, arm.offset.value) == (0, -0.5)
    load = MemberLoad(arm.number, LENGTH(0.1), LENGTH(0.3), LINE_LOAD(1), LINE_LOAD(2))
    document = frameweb_document(result.frame, one_case((load,)))
    assert member_rows(document["load"]["1"]) == [("6", "gx", 0.1, 0.2, 1, 2)]


def test_a_changed_wind_is_written_as_the_calc_gives_it(result):
    # Whatever the calc gives, the rows follow it: a trapezoid starting inside member 3.
    wind = result.basic(B.WIND_WITH_TRAIN)
    changed = replace(wind.member_loads[2], start=LENGTH(0.5), h_start=LINE_LOAD(1.25))
    document = frameweb_document(result.frame, one_case((changed,)))
    assert member_rows(document["load"]["1"]) == [("3", "gx", 0.5, 2, 1.25, 4.05)]
