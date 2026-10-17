"""0600 integration against independent Excel and VBScript expectations."""

from copy import deepcopy
from dataclasses import replace
import importlib
import json

import pytest

from src.inputs import InputError
from src.reaction_inputs import parse_reaction_input
from legacy_reaction_oracle import load_legacy_reaction_oracle, parse_legacy_reaction_input


CASES = load_legacy_reaction_oracle("reaction_excel_oracle.json")["cases"]


def calculate(inputs):
    return importlib.import_module("src.reaction_calculator").calculate_reactions(inputs)


def compare(actual, expected, *, exact=False):
    if isinstance(expected, dict):
        assert set(actual) == set(expected)
        for key, value in expected.items():
            compare(actual[key], value, exact=exact)
    elif isinstance(expected, (tuple, list)):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            compare(a, e, exact=exact)
    else:
        assert actual == (expected if exact else pytest.approx(expected, rel=1e-12, abs=1e-10))


def expected_handoff(public):
    result = {key: public[key] for key in ("桁受け", "はり", "柱", "フーチング", "上載土", "高水位", "平水位", "低水位")}
    result.update(列車荷重={}, 衝撃荷重={})
    for group, first in (("安全性", 105), ("使用性", 111)):
        result["列車荷重"][group] = {}
        result["衝撃荷重"][group] = {}
        for track, offset in (("単線", 0), ("複線", 3)):
            for target, extra in (("列車荷重", 0), ("衝撃荷重", 2)):
                result[target][group][track] = {side: public["列車反力"][f"{col}{first + offset + extra}"]
                                               for side, col in (("RB", "T"), ("RC", "X"))}
    result["地震列車"] = {side: public["地震列車"][f"地震L{side[1]}"] for side in ("RB", "RC")}
    result["線路荷重強度"] = [{side: public["線路荷重"][f"{col}{row}"] for side, col in (("RB", "T"), ("RC", "X"))}
                              for row in range(545, 555)]
    for key, cols in (("直角荷重強度", ("P", "X")), ("直角荷重位置", ("T", "AB"))):
        result[key] = [{side: public["直角荷重"][f"{col}{row}"] for side, col in zip(("RB", "RC"), cols)}
                       for row in range(185, 193)]
    result["複線分担率"] = [{"RB": public["複線分担率"]["B"][i], "RC": public["複線分担率"]["C"][i]} for i in range(10)]
    return result


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case"])
def test_all_public_values_and_exact_macro_handoff_match_independent_oracle(case):
    from reaction_combination_oracle import revised_reaction_case

    case, snow_single = revised_reaction_case(case)
    result = calculate(parse_legacy_reaction_input(case["input"]))
    compare(result["public_values"], case["public_values"])
    handoff = expected_handoff(case["public_single"])
    handoff["線路雪荷重強度"] = snow_single
    compare(result["macro_handoff_single"], handoff, exact=True)
    assert result["moving_train"]["reactions"] == tuple(case["independent_reactions"][side] for side in ("RA", "RB", "RC", "RD"))
    assert result["moving_lateral"]["reactions"][1:3] == tuple(case["independent_reactions"][side] for side in ("FB", "FC"))
    for sheet in ("列車荷重", "線路荷重", "直角荷重"):
        for cell, value in result["cells"][sheet].items():
            if cell in case["formula_values"][sheet] and isinstance(value, (int, float)):
                assert value == pytest.approx(case["formula_values"][sheet][cell], rel=1e-12, abs=1e-10), (sheet, cell)


def test_distribution_rounding_boundary_and_no_hardcoded_track_count():
    case = next(case for case in CASES if case["case"] == "distribution_slots")
    result = calculate(parse_reaction_input(case["input"]))
    assert result["cells"]["線路荷重"]["AC22"] == 639.98
    assert result["dead_loads"]["track_totals"]["B"] == pytest.approx(2.3)
    assert result["train"]["pier"]["ultimate"]["double"]["RB"]["train"] == pytest.approx(1167.9314788818358)


def test_lateral_weighted_axle_evaluation_order():
    inputs = parse_reaction_input(CASES[0]["input"])
    inputs = replace(inputs, train=replace(inputs.train, axle_load=103.75, factors_ultimate=1.22))
    result = calculate(inputs)
    assert result["cells"]["直角荷重"]["K73"] == 126.575
    assert result["cells"]["直角荷重"]["S73"] == 25.32


@pytest.mark.parametrize("hs_b,hs_c", [(0, 3.0792372881), (2.9520833333, 0)])
def test_json_hs_controls_girder_inertia_height_without_changing_other_actions(hs_b, hs_c):
    data = deepcopy(CASES[0]["input"])
    baseline = calculate(parse_reaction_input(data))
    data["上部構造"]["起点側"]["重心高_hs"] = hs_b
    data["上部構造"]["終点側"]["重心高_hs"] = hs_c
    unchanged = deepcopy(data)
    inputs = parse_reaction_input(data)
    result = calculate(inputs)
    assert (inputs.spans.b.hs, inputs.spans.c.hs) == (hs_b, hs_c)
    for actual, original in zip(result["transverse"], baseline["transverse"]):
        if actual["label"] == "地震時 桁荷重":
            for side, height in (("B", hs_b), ("C", hs_c)):
                assert actual[side]["height"] == height
                assert actual[side]["force"] == original[side]["force"]
        else:
            assert actual == original
    assert result["longitudinal"] == baseline["longitudinal"]
    assert result["weights"] == baseline["weights"]
    assert data == unchanged


@pytest.mark.parametrize("change", ["span", "length", "count", "load"])
def test_moving_reactions_recompute_for_input_changes(change):
    inputs = parse_reaction_input(CASES[0]["input"])
    baseline = calculate(inputs)
    if change == "span":
        inputs = replace(inputs, spans=replace(inputs.spans, b=replace(inputs.spans.b, span=35)))
    else:
        attrs = {"length": {"length": 22}, "count": {"n": 1}, "load": {"axle_load": 340}}[change]
        inputs = replace(inputs, train=replace(inputs.train, **attrs))
    result = calculate(inputs)
    assert result["moving_train"]["reactions"] != baseline["moving_train"]["reactions"]
    if change == "count":
        assert len(result["moving_train"]["axle_positions"]) == 4
    elif change == "load":
        assert result["moving_train"]["reactions"] == tuple(2 * value for value in baseline["moving_train"]["reactions"])


def test_zero_radius_and_factor_have_explicit_finite_results():
    inputs = parse_reaction_input(CASES[0]["input"])
    inputs = replace(inputs, spans=replace(inputs.spans, b=replace(inputs.spans.b, radius=0)),
                     train=replace(inputs.train, factors_ultimate=0))
    result = calculate(inputs)
    assert result["moving_lateral"]["reactions"] == (0, 0, 0, 0)
    assert all(row["B"]["force"] == 0 for row in result["transverse"][:4])
    assert result["train"]["pier"]["ultimate"]["single"]["RB"]["train"] == 0
    assert any("係数0" in warning for warning in result["warnings"])
    json.dumps(result, ensure_ascii=False, allow_nan=False)


def test_unused_l3_l4_changes_do_not_affect_results():
    data = deepcopy(CASES[0]["input"])
    baseline = calculate(parse_reaction_input(data))
    data["上部工反力"]["起点側"]["B支点"]["支承"][0]["列車分担"].update(L3=9, L4=99)
    changed = calculate(parse_reaction_input(data))
    assert changed["public_values"] == baseline["public_values"]
    assert any("L3" in warning for warning in changed["warnings"])


@pytest.mark.parametrize("total", [0, 0.25])
def test_signed_train_distributions_are_summed_without_normalization(total):
    data = deepcopy(CASES[0]["input"])
    expected = (-0.125, 0.125 + total, *(0.0,) * 8)
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        rows = data["上部工反力"][side][point]["支承"]
        for row in rows:
            row["列車分担"] = dict.fromkeys(("L1", "L2", "L3", "L4"), 0)
        rows[0]["列車分担"].update(L1=-0.25, L2=0.125, L3=-0.5, L4=0.25)
        rows[1]["列車分担"].update(L1=0.25 + total, L2=-0.125, L3=0.5, L4=-0.25)
    result = calculate(parse_reaction_input(data))
    for side, support in (("B", "RB"), ("C", "RC")):
        assert result["dead_loads"]["double_track_factors"][side] == expected
        assert result["dead_loads"]["track_totals"][side] == total
        assert result["macro_handoff_single"]["複線分担率"][0][f"R{side}"] == -0.125
        for group in ("ultimate", "service", "fatigue"):
            girder = result["train"]["girder"][group]
            assert girder["double"][support]["train"] == girder["single"][support]["train"] * total
    assert result["input"]["dead"]["b"][0]["factors"] == (-0.25, 0.125, -0.5, 0.25)
    json.dumps(result, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("changes", [{"n": 201}, {"axle_load": 1e100}, {"factors_ultimate": 1e308}, {"factors_ultimate": 1e-50}])
def test_invalid_or_unrepresentable_calculations_fail(changes):
    inputs = parse_reaction_input(CASES[0]["input"])
    with pytest.raises(InputError):
        calculate(replace(inputs, train=replace(inputs.train, **changes)))


def test_output_provenance_units_and_source_input_are_traceable():
    inputs = parse_reaction_input(CASES[0]["input"])
    result = calculate(inputs)
    assert result["input"]["train"]["n"] == 10
    assert result["provenance"]["source_sha256"] == "2c46fd2db477b0de8b04fc00d6c3ad223ba356f7cc2d621ece349ed61ed46f19"
    assert result["units"]["force"] == "kN"
    assert len(result["longitudinal"]) == 10
    assert len(result["transverse"]) == 8
    assert len(result["cells"]) == 5
    assert "coefficient" not in str(result["macro_handoff_single"])


def test_snow_reaches_only_its_horizontal_combinations_and_preserves_other_loads():
    data = deepcopy(CASES[0]["input"])
    baseline = calculate(parse_reaction_input(data))
    keys = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
    for side, point, multiplier, ten, thirty in (
        ("起点側", "B支点", 1, 3, 2), ("終点側", "C支点", 2, 4, 1),
    ):
        for index, row in enumerate(data["上部工反力"][side][point]["支承"]):
            row.update(dict(zip(keys, (multiplier * (index + 1), ten, thirty))))
        data["上部工反力"][side][point]["合計"] = dict.fromkeys(keys, "poisoned cached value")
    data["上部工反力"]["起点側"].setdefault("A支点", {}).setdefault("合計", {}).update({keys[0]: 10, keys[2]: 0})
    data["上部工反力"]["終点側"].setdefault("D支点", {}).setdefault("合計", {}).update(dict(zip(keys, (-5, None, -7))))
    changed = calculate(parse_reaction_input(data))
    assert changed["snow_loads"]["points"] == {
        "A": dict(zip(keys, (10, 30, 0))), "B": dict(zip(keys, (55, 30, 20))),
        "C": dict(zip(keys, (110, 40, 10))), "D": dict(zip(keys, (-5, 40, -7))),
    }
    assert changed["snow_loads"]["girders"] == {
        "AB": dict(zip(keys, (65, 60, 20))), "CD": dict(zip(keys, (105, 80, 3))),
    }
    for key in ("dead_loads", "weights", "moving_train", "moving_lateral", "train", "transverse_parameters"):
        assert changed[key] == baseline[key], key
    for side, remote, girder in (("B", "A", "AB"), ("C", "D", "CD")):
        for key in ("LR", "LR_service", "brake", "start", "braking", "design_braking", "earthquake_train"):
            assert changed["longitudinal_base"][side][key] == baseline["longitudinal_base"][side][key]
        for index in range(8):
            snow_key = keys[0 if index < 2 else 1]
            for point, field in ((remote, "remote_vertical"), (side, "local_vertical")):
                assert changed["longitudinal"][index][side][field] == pytest.approx(
                    baseline["longitudinal"][index][side][field] + changed["snow_loads"]["points"][point][snow_key])
        for index in range(2):
            for point, field in ((remote, "remote_vertical"), (side, "local_vertical")):
                assert changed["longitudinal_snow_cases"][index][side][field] == pytest.approx(
                    baseline["longitudinal_snow_cases"][index][side][field] + changed["snow_loads"]["points"][point][keys[2]])
        earthquake = changed["longitudinal"][8][side]
        assert earthquake["applied"] == baseline["longitudinal"][8][side]["applied"] + changed["snow_loads"]["girders"][girder][keys[0]]
        assert earthquake["force"] == earthquake["applied"] * (1 if earthquake["bearing"] == "固定" else .5)
        assert changed["transverse"][6][side]["force"] == baseline["transverse"][6][side]["force"] + changed["snow_loads"]["points"][side][keys[0]]
        assert changed["transverse"][6][side]["height"] == baseline["transverse"][6][side]["height"]
    for key in ("列車荷重", "衝撃荷重", "地震列車", "直角荷重位置"):
        assert changed["macro_handoff_single"][key] == baseline["macro_handoff_single"][key]
    assert changed["transverse"][:6] == baseline["transverse"][:6]
    assert changed["transverse"][7] == baseline["transverse"][7]
    assert changed["longitudinal"][9] == baseline["longitudinal"][9]
    assert changed["snow_loads"]["slots"]["B"] == [dict(zip(keys, (index + 1, 3, 2))) for index in range(10)]
    assert changed["snow_loads"]["slots"]["C"] == [dict(zip(keys, (2 * (index + 1), 4, 1))) for index in range(10)]
    before_input, after_input = deepcopy(baseline["input"]), deepcopy(changed["input"])
    del before_input["snow"], after_input["snow"]
    assert before_input == after_input
    assert set(changed["snow_loads"]) == {"points", "girders", "slots"}
    assert len(changed["cells"]) == 5
    assert "ユーザー入力" in changed["provenance"]["snow_loads"]
    assert "元Excel" in changed["provenance"]["snow_loads"]
    assert "水平荷重" in changed["provenance"]["snow_loads"]
    json.dumps(changed, ensure_ascii=False, allow_nan=False)


def test_legacy_snow_results_are_zero_and_do_not_add_dead_load_fields():
    result = calculate(parse_reaction_input(CASES[0]["input"]))
    keys = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
    for point in result["snow_loads"]["points"].values():
        assert point == dict.fromkeys(keys, 0)
    for girder in result["snow_loads"]["girders"].values():
        assert girder == dict.fromkeys(keys, 0)
    for side in ("B", "C"):
        assert result["snow_loads"]["slots"][side] == [dict.fromkeys(keys, 0)] * 10
    assert all(set(point) == {"D1", "D2", "total"} for point in result["dead_loads"]["points"].values())


def test_snow_aggregate_overflow_is_a_path_qualified_input_error():
    data = deepcopy(CASES[0]["input"])
    data["上部工反力"]["起点側"]["B支点"]["支承"][9]["雪荷重_30年確率"] = 1e308
    with pytest.raises(InputError, match=r"上部工反力\.起点側\.A支点\.合計\.雪荷重_30年確率"):
        calculate(parse_reaction_input(data))
