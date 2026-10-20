"""FrameWeb load cases: Example2 08 pp.8-6 to 8-9 and its FrameWeb file.

Signs (FrameWeb in the current axes, y downward, decision 44): tx = H, ty = N (N downward), rz = M (M positive as
N × +x lever: Example2 D1 M = −610.00 is rz = −610; the old-format Example2 file saves ty = −N, rz = 610). A component
that is 0 is saved as null, as FrameWeb does.
"""

import pytest

from frameweb_support import ASYMMETRIC, CENTRED_PEDESTAL, EXAMPLE2, L08, PEDESTAL, longitudinal, mirrored_rows
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import BasicCase
from webpier.export.frameweb import build_frameweb

# Example2 prints these from unrounded intermediates; we use the printed operands (see tests/calc):
# 8-4 L2 1134.77 / 221.04 -> 1134.78 / 221.03, 8-5 I1 227.78 / 86.99 -> 227.79 / 87.00, I2 428.28 -> 428.29.
# The Example2 FrameWeb file also has I1 / I2 of these values.
DIFFERENT = {"10": [("1", None, 1134.78, 221.03)], "11": [("1", None, 227.79, 87)],
             "12": [("1", None, 428.29, 168.11)]}


@pytest.fixture(scope="module")
def result():
    return longitudinal()


@pytest.fixture(scope="module")
def current(result):
    return build_frameweb(result)


def node_rows(case):
    return [(row["n"], row["tx"], row["ty"], row["rz"]) for row in case.get("load_node", [])]


def test_basic_load_cases_are_those_of_example2(current):
    for number in map(str, range(1, 21)):
        expected = DIFFERENT.get(number, mirrored_rows(node_rows(EXAMPLE2["load"][number])))
        assert node_rows(current["load"][number]) == expected, number


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
    for number in range(1, 21):
        case, example = current["load"][str(number)], EXAMPLE2["load"][str(number)]
        assert list(case)[:6] == ["fix_node", "element", "symbol", "LL_pitch", "rate", "name"]
        assert case["fix_node"] == printed[number]
        assert case["fix_node"] == example["fix_node"] or number in EXAMPLE2["known_differences"]["spring_cases"]
        assert (case["element"], case["LL_pitch"], case["rate"]) == (1, 0.1, 1)
        assert case["symbol"] == example["symbol"]
        # Example2 names 18 and 20 "ﾛﾝｸﾞﾚｰﾙ+制動" though they carry the rail force only (8-9: ﾛﾝｸﾞﾚｰﾙ縦荷重).
        assert case["name"] == {18: "ﾛﾝｸﾞﾚｰﾙ縦荷重　安全性", 20: "ﾛﾝｸﾞﾚｰﾙ縦荷重　復旧性"}.get(number, example["name"])


def test_serviceability_impacts_are_two_more_load_cases(current, result):
    # The serviceability impact (8-5, 0.75 i already in the 0600 girder coefficient) is another action than the
    # basic I; combinations 5, 7, 15 and 16 analyse it, so it is a load case of its own after the 20 basic cases.
    assert list(current["load"]) == [str(n) for n in range(1, 23)]
    for number, impact in (("21", result.impact.service_single), ("22", result.impact.service_double)):
        case = current["load"][number]
        assert (case["fix_node"], case["symbol"]) == (2, {"21": "I1s", "22": "I2s"}[number])
        assert case["name"] == {"21": "衝撃荷重　使用性　単線", "22": "衝撃荷重　使用性　複線"}[number]
        assert node_rows(case) == [("1", None, impact.n.value, impact.m.value)]
    # Hand, 8-4 single track × 07 7-2 serviceability coefficients 0.184 / 0.41: 272.47 × 0.184 = 50.134 -> 50.13,
    # 294.92 × 0.41 = 120.917 -> 120.92, N = 171.05; 50.13 × −0.325 = −16.29, 120.92 × 0.675 = 81.62, M = 65.33.
    assert node_rows(current["load"]["21"]) == [("1", None, 171.05, 65.33)]


def test_every_load_is_the_printed_action(current, result):
    # Values are copied from the calc result: no rounding, no scaling.
    actions = [*result.basic_cases, *(c.source for c in (result.combinations[6].components[1],
                                                         result.combinations[4].components[4]))]
    for number, action in enumerate(actions, 1):
        case = current["load"][str(number)]
        expected = [(str(p.node), p.h.value or None, p.n.value or None, p.m.value or None)
                    for p in action.points if (p.n.value, p.h.value, p.m.value) != (0, 0, 0)]
        assert node_rows(case) == expected


def test_pedestal_loads_act_at_the_pedestal_top():
    # Decision 29: the bearing loads at the pedestal top (node 1); the pier parts at the beam top (node 3).
    # Nodes numbered from the upper left (JRSNAP 2.1.6): pedestal top 1, base 2, beam top 3; the footing centroid 7.
    result = longitudinal(**PEDESTAL)
    document = build_frameweb(result)
    seat = str(result.frame.node(NodeRole.PEDESTAL_TOP).number)
    assert node_rows(document["load"]["1"]) == [(seat, None, 7600, 2050), ("3", None, 750.98, -18.01),
                                                ("7", None, 4167.45, None)]
    assert node_rows(document["load"]["15"]) == [(seat, 473.43, None, None)]
    # The serviceability impact moves to the seat as well: M − N × (−0.350).
    single = result.impact.service_single
    (row,) = node_rows(document["load"]["21"])
    assert row[:3] == (seat, None, single.n.value)
    assert row[3] == result.combinations[6].component(BasicCase.IMPACT_SINGLE).source.points[0].m.value
    assert [r["m1"] for r in document["load"]["1"]["load_member"]] == ["3", "4", "5"]  # not on the pedestal (1, 2)


def test_centred_pedestal_moments_are_unchanged():
    document = build_frameweb(longitudinal(**CENTRED_PEDESTAL))
    assert node_rows(document["load"]["2"])[0] == ("1", None, 780, 6.5)  # the pedestal top is node 1


def test_asymmetric_footing_loads_keep_their_levers():
    result = longitudinal(**ASYMMETRIC)
    document = build_frameweb(result)
    footing = result.fixed.footing
    assert footing.m.value != 0
    assert node_rows(document["load"]["1"])[1] == ("5", None, footing.n.value, footing.m.value)
