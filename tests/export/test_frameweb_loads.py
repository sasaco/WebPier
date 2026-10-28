"""FrameWeb load cases: Example2 08 pp.8-6 to 8-9 and its FrameWeb file.

Signs (FrameWeb in the current axes, y downward, decision 44): tx = H, ty = N (N downward), rz = M (M positive as
N × +x lever: Example2 D1 M = −610.00 is rz = −610; the old-format Example2 file saves ty = −N, rz = 610). A component
that is 0 is saved as null, as FrameWeb does.
"""

import pytest

from frameweb_support import (ASYMMETRIC, CENTRED_PEDESTAL, EXAMPLE2, EXAMPLE2_DROPPED, L08, PEDESTAL, REDUCED,
                              example2_cases, first_placing, longitudinal, mirrored_rows)
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import Basis, BasicCase, Check, Layout
from webpier.export.frameweb import build_frameweb

# By Example2's number. Example2 prints these from unrounded intermediates; we use the printed operands (see
# tests/calc): 8-4 L2 1134.77 / 221.04 -> 1134.78 / 221.03. Decision 77: the impact is on the pier body, so I2 differs
# from Example2 8-5 (428.28 / 168.11), which has no reduction: 92.09 + 234.76 = 326.85, −29.93 + 158.46 = 128.53 (hand:
# test_longitudinal_loads). Decision 119: case 17 (1.0LR+1.35B) takes Rm without impact: 308.00 + 188.62 = 496.62
# (Example2 495.01; hand: test_longitudinal_loads WITHOUT_IMPACT).
DIFFERENT = {"10": [("1", None, 1134.78, 221.03)], "12": [("1", None, 326.85, 128.53)],
             "17": [("1", 496.62, None, None)]}


@pytest.fixture(scope="module")
def result():
    return longitudinal()


@pytest.fixture(scope="module")
def full(result):
    return build_frameweb(result)


@pytest.fixture(scope="module")
def current(full):
    """The file of ① only, as Example2's (decision 102)."""
    return first_placing(full)


def node_rows(case):
    return [(row["n"], row["tx"], row["ty"], row["rz"]) for row in case.get("load_node", [])]


def test_basic_load_cases_are_those_of_example2(current):
    for number, ours in example2_cases(current).items():
        expected = DIFFERENT.get(number, mirrored_rows(node_rows(EXAMPLE2["load"][number])))
        assert node_rows(current["load"][ours]) == expected, number


def test_the_single_track_train_and_impact_are_not_load_cases(full):
    # decision 120 (g): no combination of Example橋脚4 表2.3.2 takes the single-track train or impact, so Example2's
    # cases 9 (L1) and 11 (I1) and the serviceability I1s are not in the file.
    assert {EXAMPLE2["load"][n]["symbol"] for n in EXAMPLE2_DROPPED} == {"L1", "I1"}
    symbols = {case["symbol"].split("-")[0] for case in full["load"].values()}
    assert not symbols & {"L1", "I1", "I1s"}


def test_the_reduced_dead_load_cases_follow_their_twins(current, result):
    # Decision 120: 1.1LR+1.0B and 1.0LR+1.1B again with 0.9 D1 + 0.8 D2 in 0600's Rm, right after the twin; the same
    # label with 死荷重低減あり, short-term springs, the bearing force of the reduced 0600 case.
    reduced = [(n, case) for n, case in current["load"].items() if REDUCED in case["name"]]
    assert [(n, case["symbol"], case["name"], case["fix_node"]) for n, case in reduced] == [
        ("15", "1.1LR+1.0B", "ﾛﾝｸﾞﾚｰﾙ+制動　安全性　死荷重低減あり", 2),
        ("17", "1.0LR+1.1B", "ﾛﾝｸﾞﾚｰﾙ+制動　安全性　死荷重低減あり", 2)]
    assert [current["load"][n]["symbol"] for n in ("14", "16")] == ["1.1LR+1.0B", "1.0LR+1.1B"]
    for (number, case), basic in zip(reduced, (BasicCase.SAFETY_LR11_B_REDUCED, BasicCase.SAFETY_LR10_BMAX_REDUCED),
                                     strict=True):
        (action,) = [a for a in result.basic_cases if a.case is basic and a.layout is Layout.BOTH]
        (point,) = action.points
        assert node_rows(case) == [(str(point.node), point.h.value, None, None)], number


def test_node_rows_have_the_example2_layout(current):
    for case in current["load"].values():
        for index, row in enumerate(case.get("load_node", []), 1):
            assert list(row) == ["n", "tx", "ty", "tz", "rx", "ry", "rz", "row"]
            assert (row["tz"], row["rx"], row["ry"], row["row"]) == (None, None, None, index)


def test_the_column_line_load_is_one_row_per_member(current):
    # Example2 saves q = 297.68 on members 1-3 as one range row in the local x of the members (downward, from the
    # beam top). We save one row per member in the global y (downward +): the same load on these vertical members,
    # and it does not depend on the members being numbered in a row or on their orientation.
    (example,) = [row for row in EXAMPLE2["load"]["1"]["load_member"]]
    assert (example["m1"], example["m2"], example["direction"], example["P1"]) == ("1", "3", "x", 297.68)
    assert current["load"]["1"]["load_member"] == [
        {"m1": str(m), "m2": str(m), "direction": "gy", "mark": 2, "L1": 0, "L2": 0, "P1": 297.68, "P2": 297.68,
         "row": m} for m in (1, 2, 3)]
    for member in ("1", "2", "3"):
        ni, nj = (current["node"][str(current["member"][member][end])] for end in ("ni", "nj"))
        assert ni["x"] == nj["x"] and ni["y"] < nj["y"]  # vertical, from top to bottom: local x = gy


def test_only_d1_has_member_loads_and_empty_cases_have_no_rows(current):
    # Example2 saves empty member rows ({"P1": null, ...}); FrameWeb rejects them (unsupported mark), so a case
    # without loads has no load_node / load_member at all, as in Example2 case 5 (WP3, low water 0.00).
    assert [n for n, case in current["load"].items() if "load_member" in case] == ["1"]
    assert "load_node" not in current["load"]["5"] and "load_node" not in EXAMPLE2["load"]["5"]


def test_load_case_headers(current):
    # fix_node is the spring set of 8-9 (1 long-term, 2 short-term). The Example2 file saves 2 for cases 14, 18 and
    # 20 where 8-9 prints 1; we follow 8-9.
    printed = {row["no"]: row["spring"] for row in L08["basic_cases"]["rows"]}
    for example_number, ours in example2_cases(current).items():
        number = int(example_number)
        case, example = current["load"][ours], EXAMPLE2["load"][example_number]
        assert list(case)[:6] == ["fix_node", "element", "symbol", "LL_pitch", "rate", "name"]
        assert case["fix_node"] == printed[number]
        assert case["fix_node"] == example["fix_node"] or number in EXAMPLE2["known_differences"]["spring_cases"]
        assert (case["element"], case["LL_pitch"], case["rate"]) == (1, 0.1, 1)
        assert case["symbol"] == example["symbol"]
        # Example2 names 18 and 20 "ﾛﾝｸﾞﾚｰﾙ+制動" though they carry the rail force only (8-9: ﾛﾝｸﾞﾚｰﾙ縦荷重).
        assert case["name"] == {18: "ﾛﾝｸﾞﾚｰﾙ縦荷重　安全性", 20: "ﾛﾝｸﾞﾚｰﾙ縦荷重　復旧性"}.get(number, example["name"])


def test_the_serviceability_impact_is_one_more_load_case(current, result):
    # The serviceability impact (8-5, 0.75 i already in the 0600 serviceability coefficient) is another action than the
    # basic I; the edge-stress and variable combinations analyse it (decision 120: of the double track only), so it is
    # a load case of its own after the 20 basic cases of ①.
    assert list(current["load"]) == [str(n) for n in range(1, 22)]
    case, impact = current["load"]["21"], result.impact.service_double
    assert (case["fix_node"], case["symbol"], case["name"]) == (2, "I2s", "衝撃荷重　使用性　複線")
    assert node_rows(case) == [("1", None, impact.n.value, impact.m.value)]


def test_every_load_is_the_printed_action(full, result):
    # Values are copied from the calc result: no rounding, no scaling. After the 38 basic cases, the serviceability
    # impact I2s of ①, ② and ③ (decisions 102, 120).
    service = {(k.case, c.layout): k.source for c in result.combinations for k in c.components
               if k.basis is Basis.SERVICE_IMPACT}
    assert set(service) == {(BasicCase.IMPACT_DOUBLE, layout) for layout in Layout}
    actions = [*result.basic_cases, *(service[(BasicCase.IMPACT_DOUBLE, layout)] for layout in Layout)]
    assert len(result.basic_cases) == 38
    assert len(full["load"]) == len(actions) == 41
    for number, action in enumerate(actions, 1):
        case = full["load"][str(number)]
        expected = [(str(p.node), p.h.value or None, p.n.value or None, p.m.value or None)
                    for p in action.points if (p.n.value, p.h.value, p.m.value) != (0, 0, 0)]
        assert node_rows(case) == expected


def test_pedestal_loads_act_at_the_pedestal_top():
    # Decisions 29, 80: both girders on the pedestal, their loads at its top (node 1) with the levers from its
    # centre +0.175 (5740 × (−0.500) + 1860 × 0.500 = −1940.00); the beam at the beam top (node 2).
    # Nodes numbered from the upper left (JRSNAP 2.1.6): pedestal top 1, beam top 2, base 3; the footing centroid 7.
    result = longitudinal(**PEDESTAL)
    document = first_placing(build_frameweb(result))  # Example2's numbers (decision 102)
    seat = str(result.frame.node(NodeRole.PEDESTAL_TOP).number)
    assert node_rows(document["load"]["1"]) == [("2", None, 699.53, None), (seat, None, 7600, -1940),
                                                ("7", None, 4167.45, None)]
    assert node_rows(document["load"][example2_cases(document)["15"]]) == [(seat, 473.43, None, None)]
    # The serviceability impact moves to the seat as well: M − N × 0.175.
    double = result.impact.service_double
    (row,) = node_rows(document["load"]["21"])
    assert row[:3] == (seat, None, double.n.value)
    variable = next(c for c in result.combinations if c.check is Check.CRACK_VARIABLE and c.layout is Layout.BOTH)
    assert row[3] == variable.component(BasicCase.IMPACT_DOUBLE).source.points[0].m.value
    # The pedestal weight q = 7.000 × 1.000 × 24.5 along it (member 1, decision 81), then the column line; not the arm.
    assert [(r["m1"], r["P1"]) for r in document["load"]["1"]["load_member"]] == [
        ("1", 171.5), ("3", 297.68), ("4", 297.68), ("5", 297.68)]


def test_centred_pedestal_moments_are_unchanged():
    document = build_frameweb(longitudinal(**CENTRED_PEDESTAL))
    assert node_rows(document["load"]["2"])[0] == ("1", None, 780, 6.5)  # the pedestal top is node 1


def test_asymmetric_footing_loads_keep_their_levers():
    result = longitudinal(**ASYMMETRIC)
    document = build_frameweb(result)
    footing = result.fixed.footing
    assert footing.m.value != 0
    assert node_rows(document["load"]["1"])[1] == ("5", None, footing.n.value, footing.m.value)
