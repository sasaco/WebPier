"""Readback of a FrameWeb file through FrameWebforCS.Headless: counts, skipped cases and the applied loads.

A load case without rows is skipped by FrameWeb (README FrameWeb), and so is a Define whose cases are all such
cases; everything else must come back. For every calculated case, the support reactions must balance the loads we
wrote, so a load that was dropped or misread shows. The documents and results here are small literal ones.
"""

import pytest

from frameweb_support import longitudinal
from webpier.export.frameweb import build_frameweb
from webpier.export.frameweb.readback import (
    ReadbackError, applied_totals, check_equilibrium, combination_vertical, compare_counts, expected_counts,
)


def node_load(n, tx=None, ty=None, rz=None, row=1):
    return {"n": n, "tx": tx, "ty": ty, "tz": None, "rx": None, "ry": None, "rz": rz, "row": row}


def member_load(m, direction, p1, p2, l1=0, l2=0, row=1):
    return {"m1": m, "m2": m, "direction": direction, "mark": 2, "L1": l1, "L2": l2, "P1": p1, "P2": p2, "row": row}


def document():
    """Two members along y (4 m and 2 m), three cases: loaded, empty, loaded; a Define of the empty case only."""
    return {
        "node": {"1": {"x": 0, "y": 6, "z": None}, "2": {"x": 0, "y": 2, "z": None}, "3": {"x": 0, "y": 0, "z": None}},
        "member": {"1": {"ni": 1, "nj": 2, "e": 1, "cg": None}, "2": {"ni": 2, "nj": 3, "e": 1, "cg": None}},
        "load": {"1": {"symbol": "D1", "load_node": [node_load("1", ty=-100)],
                       "load_member": [member_load("1", "gy", -10, -10), member_load("2", "gx", 2, 4, l1=0.5, l2=0.5,
                                                                                      row=2)]},
                 "2": {"symbol": "Wp3"},
                 "3": {"symbol": "W", "load_node": [node_load("2", tx=5, rz=3)]}},
        "define": {"1": {"row": 1, "C1": 1}, "2": {"row": 2, "C1": 2}, "3": {"row": 3, "C1": 3, "C2": -3}},
        "combine": {"1": {"row": 1, "C1": 1, "C2": 1, "C3": 1}},
        "pickup": {"1": {"row": 1, "C1": 1}},
    }


def reaction(node, fx=0.0, fy=0.0):
    return {"node_id": node, "components": {"fx": fx, "fy": fy, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0}}


def result(**changes):
    value = {
        "skippedLoadCases": ["2"],
        "analysisResultSet": {
            "cases": [{"case_id": "1"}, {"case_id": "3"}],
            "topology": {"nodes": [{"node_id": "1"}, {"node_id": "2"}, {"node_id": "3"},
                                   {"node_id": "generated:2:S1", "generated": True}],
                         "members": [{"member_id": "1"}, {"member_id": "2"}]},
            "results": [{"case_id": "1", "support_reactions": [reaction("1"), reaction("3", fx=-3.0, fy=140.0)]},
                        {"case_id": "3", "support_reactions": [reaction("3", fx=-5.0)]}],
        },
        "derived": {"defines": [{"id": "1"}, {"id": "3"}], "combines": [{"id": "1"}], "pickups": [{"id": "1"}]},
    }
    value.update(changes)
    return value


def envelope(**changes):
    value = {"ok": True, "executionStatus": "success", "errors": [],
             "summary": {"nodes": 4, "members": 2, "cases": 2, "results": 2, "pickups": 1, "skippedLoadCases": 1}}
    value.update(changes)
    return value


def test_expected_counts_of_a_document():
    assert expected_counts(document()) == {"nodes": 3, "members": 2, "load_cases": 3, "empty_load_cases": ["2"],
                                           "defines": 3, "defines_without_loads": ["2"], "combines": 1, "pickups": 1}


def test_the_current_input_has_one_empty_case():
    """current.json: the low-water buoyancy Wp3 (case 5) is zero, so it has no rows and its Define 5 is skipped."""
    counts = expected_counts(build_frameweb(longitudinal()))
    assert (counts["empty_load_cases"], counts["defines_without_loads"]) == (["5"], ["5"])
    # 38 basic cases (each case of the train for ①, ② and ③, decision 102) and the 6 serviceability impacts
    assert (counts["load_cases"], counts["defines"], counts["combines"], counts["pickups"]) == (44, 44, 38, 8)


def test_counts_that_come_back():
    assert compare_counts(document(), envelope(), result()) == {
        "nodes": 3, "generated_nodes": 1, "members": 2, "calculated_cases": 2, "skipped_load_cases": ["2"],
        "defines": 2, "combines": 1, "pickups": 1}


@pytest.mark.parametrize("changes,message", [
    ({"ok": False}, "成功していません"),
    ({"executionStatus": "failed"}, "成功していません"),
    ({"errors": [{"code": "X"}]}, "成功していません"),
    ({"summary": {"nodes": 4, "members": 2, "cases": 3, "results": 2, "pickups": 1, "skippedLoadCases": 1}},
     "summary"),
])
def test_a_failed_or_inconsistent_envelope_is_an_error(changes, message):
    with pytest.raises(ReadbackError, match=message):
        compare_counts(document(), envelope(**changes), result())


def mutate(path, value):
    changed = result()
    node = changed
    *parents, key = path
    for part in parents:
        node = node[part]
    node[key] = value
    return changed


@pytest.mark.parametrize("changed,message", [
    (mutate(("analysisResultSet", "topology", "nodes"), [{"node_id": "1"}, {"node_id": "2"}]), "節点"),
    (mutate(("analysisResultSet", "topology", "members"), [{"member_id": "1"}]), "部材"),
    (mutate(("skippedLoadCases",), []), "飛ばした荷重ケース"),
    (mutate(("analysisResultSet", "cases"), [{"case_id": "1"}]), "計算した荷重ケース"),
    (mutate(("derived", "defines"), [{"id": "1"}]), "Define"),
    (mutate(("derived", "combines"), []), "Combine"),
    (mutate(("derived", "pickups"), []), "Pickup"),
])
def test_a_count_that_does_not_come_back_is_an_error(changed, message):
    summary = {"nodes": len(changed["analysisResultSet"]["topology"]["nodes"]),
               "members": len(changed["analysisResultSet"]["topology"]["members"]),
               "cases": len(changed["analysisResultSet"]["cases"]),
               "results": len(changed["analysisResultSet"]["results"]),
               "pickups": len(changed["derived"]["pickups"]), "skippedLoadCases": len(changed["skippedLoadCases"])}
    with pytest.raises(ReadbackError, match=message):
        compare_counts(document(), envelope(summary=summary), changed)


def test_applied_totals_of_node_and_member_loads():
    # Case 1: −100 at node 1, −10 kN/m over member 1 (4 m), 2 → 4 kN/m over member 2 less 0.5 m at each end (1 m).
    assert applied_totals(document(), "1") == pytest.approx((3.0, -140.0))
    assert applied_totals(document(), "3") == pytest.approx((5.0, 0.0))
    assert applied_totals(document(), "2") == (0.0, 0.0)


@pytest.mark.parametrize("row,message", [({"direction": "x"}, "向き x"), ({"mark": 1}, "種類 1")])
def test_an_unknown_member_load_is_an_error(row, message):
    changed = document()
    changed["load"]["1"]["load_member"][0].update(row)
    with pytest.raises(ReadbackError, match=message):
        applied_totals(changed, "1")


def test_reactions_balance_the_loads_we_wrote():
    assert check_equilibrium(document(), result()) == [
        {"case": "1", "symbol": "D1", "applied": [3.0, -140.0], "reactions": [-3.0, 140.0]},
        {"case": "3", "symbol": "W", "applied": [5.0, 0.0], "reactions": [-5.0, 0.0]}]


def test_a_load_that_did_not_survive_is_an_error():
    changed = result()
    changed["analysisResultSet"]["results"][0]["support_reactions"][1]["components"]["fx"] = -6.0
    with pytest.raises(ReadbackError, match="荷重ケース 1（D1）: 荷重 fx = 3.*反力 fx = -6"):
        check_equilibrium(document(), changed)


def test_a_case_without_result_is_an_error():
    changed = result()
    changed["analysisResultSet"]["results"].pop()
    with pytest.raises(ReadbackError, match="荷重ケース 3 の結果がありません"):
        check_equilibrium(document(), changed)


def combine_result(upward, upward_min=None):
    """A Combine whose support holds *upward* (fy = −upward: the file's y is downward, decision 44)."""
    entry = {"entityId": "6", "components": {"fx": 0.0, "fy": -upward}}
    low = {"entityId": "6", "components": {"fx": 0.0, "fy": -(upward if upward_min is None else upward_min)}}
    return {"derived": {"combines": [{"id": "1", "reactions": {"fy_max": [entry], "fy_min": [low]}}]}}


@pytest.fixture(scope="module")
def combination_1():
    result = longitudinal()
    return result.combinations[0], build_frameweb(result)


def test_a_combination_differs_from_the_printed_one_only_by_rounding_each_action(combination_1):
    """Decision 38, current.json 0610 combination 1 (破壊 列車最大), by hand:

    printed:   9129.48 + 4584.2 + 327.45 × 7.6 + 936.0 + 2196.72 + 1140.0 + 1531.95 + 441.25 = 22448.220
    unrounded: 1.1 × (8299.53 + 4167.45 + 297.68 × 7.6) + 1.2 × (780.0 + 1830.6) + 1140.0 + 1.35 × 1134.78
               + 1.35 × 326.85 = 22448.2033   (decision 77: the double-track impact 92.09 + 234.76 = 326.85)
    The largest action difference is 4584.2 − 1.1 × 4167.45 = 0.005.
    """
    combination, document = combination_1
    checked = combination_vertical(combination, document, combine_result(22448.2033))
    assert checked["printed"] == pytest.approx(22448.22, abs=1e-9)
    assert checked["unrounded"] == pytest.approx(22448.2033, abs=1e-9)
    assert checked["frameweb"] == 22448.2033
    assert checked["difference"] == pytest.approx(0.0167, abs=1e-9)
    assert checked["largest_action_difference"] == pytest.approx(0.005, abs=1e-9)


def test_a_combined_reaction_that_is_not_the_unrounded_sum_is_an_error(combination_1):
    combination, document = combination_1
    with pytest.raises(ReadbackError, match="Combine 1: 鉛直反力 22448.22"):
        combination_vertical(combination, document, combine_result(22448.22))


def test_a_vertical_reaction_with_alternatives_is_not_a_spot_check(combination_1):
    combination, document = combination_1
    with pytest.raises(ReadbackError, match="Combine 1: 鉛直反力の最大と最小が異なります"):
        combination_vertical(combination, document, combine_result(22448.2033, upward_min=22000.0))


def test_an_action_rounded_by_more_than_decision_38_allows_is_an_error(combination_1):
    from dataclasses import replace

    from webpier.core.printed import Printed
    combination, document = combination_1
    first = combination.components[0]
    point = replace(first.points[1], n=Printed(4584.3, 1, first.points[1].n.unit))
    changed = replace(combination, components=(replace(first, points=(first.points[0], point)),
                                               *combination.components[1:]))
    with pytest.raises(ReadbackError, match="0.005 を超えます"):
        combination_vertical(changed, document, combine_result(22448.2033))
