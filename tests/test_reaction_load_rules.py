"""Vehicle-specific longitudinal load rules, independent of bearing choices."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import json
import struct

import pytest

from src.inputs import InputError
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from legacy_reaction_oracle import load_legacy_reaction_oracle


ORACLE = load_legacy_reaction_oracle("reaction_excel_oracle.json")["cases"][0]


def example_train_input(name="EC-16"):
    data = deepcopy(ORACLE["input"])
    structure = data["上部構造"]
    for side, span in (("起点側", 19.0), ("終点側", 9.0)):
        structure[side]["桁長"].update(L1=0.5, スパン長=span, L2=0.5)
    train = structure["列車"]
    train["車両名"] = name
    train["1両の長さ"]["値"] = 20.0
    train["軸重"]["地震以外"]["値"] = 160.0
    train["荷重修正係数"]["安全性(破壊)"] = 1.0
    return data


def example2_horizontal_input():
    """Freeze the independent Example 2 workbook's horizontal-load inputs."""
    data = example_train_input("P-16")
    for side, span, end, impact, dead, snow, factors, outer_d2, bearing in (
        ("起点側", 18.85, .575, .245, ((1530, 160), (1340, 100), (1340, 100), (1530, 160)),
         ((200, 320, 360), (30, 50, 50), (30, 50, 50), (200, 320, 360)),
         ((.471, -.02), (.373, .176), (.176, .373), (-.02, .471)), 660, "可動"),
        ("終点側", 9.25, .375, .546, ((930, 130), (930, 130)),
         ((125, 200, 225), (125, 200, 225)), ((.857, .143), (.143, .857)), 260, "固定"),
    ):
        local, remote = ("B支点", "A支点") if side == "起点側" else ("C支点", "D支点")
        data["上部構造"][side]["桁長"].update(L1=end, スパン長=span, L2=end)
        data["上部構造"][side]["衝撃係数"]["単線終局"] = impact
        data["上部構造"]["支承データ"][side].update(支承名=bearing, 摩擦係数_μ=.1)
        branch = data["上部工反力"][side]
        for index, row in enumerate(branch[local]["支承"]):
            d1, d2 = dead[index] if index < len(dead) else (0, 0)
            row.update(固定死荷重_D1=d1, 付加死荷重_D2=d2)
            row.update(dict(zip(SNOW_KEYS, snow[index] if index < len(snow) else (0, 0, 0))))
            f1, f2 = factors[index] if index < len(factors) else (0, 0)
            row["列車分担"].update(L1=f1, L2=f2, L3=0, L4=0)
        branch.setdefault(remote, {})["合計"] = {
            "固定死荷重_D1": sum(row[0] for row in dead), "付加死荷重_D2": outer_d2,
            **dict(zip(SNOW_KEYS, map(sum, zip(*snow)))),
        }
    train = data["上部構造"]["列車"]
    train["軸距"].update(a1_連結部=2.8, a2=2.2)
    train["荷重修正係数"]["安全性(破壊)"] = 1.231
    data["上部構造"]["支承データ"]["終点側"]["復旧性制動係数"] = 1.0
    return data


def test_example2_verticals_and_bearing_forces_follow_source_expanded_formulas():
    result = calculate_reactions(parse_reaction_input(example2_horizontal_input()))
    # Source workbook 線路水平 J111/J127, J150/J166, J184/J200.
    for index, b, c in ((1, 7355.9375751342777, 2439.7756639404297),
                        (4, 8576.9770502990723, 2861.0006179382326),
                        (5, 8497.0679791613784, 2851.8450074548341)):
        assert result["longitudinal"][index]["B"]["local_vertical"] == pytest.approx(b, rel=0, abs=1e-9)
        assert result["longitudinal"][index]["C"]["remote_vertical"] == pytest.approx(c, rel=0, abs=1e-9)
    assert result["longitudinal"][6]["combination"]["include_impact"] is True
    assert result["longitudinal"][6]["C"]["force"] == 187.01
    assert result["longitudinal"][7]["C"]["force"] == 165.31


@pytest.mark.parametrize("coefficient", [None, 0, 1, 1.234])
def test_recovery_brake_override_is_side_specific_and_only_changes_recovery(coefficient):
    data = example2_horizontal_input()
    support = data["上部構造"]["支承データ"]["終点側"]
    support.pop("復旧性制動係数")
    baseline = calculate_reactions(parse_reaction_input(data))
    support["復旧性制動係数"] = coefficient
    changed = calculate_reactions(parse_reaction_input(data))
    for index in range(10):
        assert changed["longitudinal"][index]["B"] == baseline["longitudinal"][index]["B"]
        if index != 7:
            assert changed["longitudinal"][index]["C"] == baseline["longitudinal"][index]["C"]
    effective = 1.23 if coefficient is None else coefficient
    recovery = changed["longitudinal"][7]
    assert recovery["B"]["effective_brake_coefficient"] == 1.23
    assert recovery["C"]["effective_brake_coefficient"] == effective
    assert recovery["C"]["applied"] == pytest.approx(200 + effective * 96)


@pytest.mark.parametrize("override, expected_brake", [(None, 0), (0, 0), (1, 102.4)])
def test_ea17_zero_rho_recovery_override_uses_uncorrected_raw_braking(override, expected_brake):
    data = example2_horizontal_input()
    vehicle = data["上部構造"]["列車"]
    vehicle["車両名"] = "EA-17"
    vehicle["荷重修正係数"]["安全性(破壊)"] = 0
    data["上部構造"]["支承データ"]["終点側"]["復旧性制動係数"] = override
    result = calculate_reactions(parse_reaction_input(data))
    recovery = result["longitudinal"][7]
    # Source raw RC+RD=320; max((.27+1/20)*320, (.25+.95/20)*320)=102.40.
    assert recovery["C"]["applied"] == pytest.approx(200 + expected_brake)
    assert recovery["C"]["braking_contribution"] == expected_brake
    assert recovery["B"]["applied"] == 400
    assert result["longitudinal_base"]["C"]["braking"] == 0


@pytest.mark.parametrize("name", ["EA-17", "EC-16"])
def test_train_name_is_preserved_in_reaction_input(name):
    inputs = parse_reaction_input(example_train_input(name))
    assert getattr(inputs.train, "name", None) == name


def test_ea17_brake_and_start_preserve_independent_excel_values():
    result = calculate_reactions(parse_reaction_input(deepcopy(ORACLE["input"])))
    expected = ORACLE["formula_values"]["線路荷重"]
    for side, brake_cell, start_cell in (("B", "AC44", "AC50"), ("C", "AC46", "AC52")):
        assert result["longitudinal_base"][side]["brake"] == expected[brake_cell]
        assert result["longitudinal_base"][side]["start"] == expected[start_cell]


@pytest.mark.parametrize("name", ["EC-16", "another train"])
def test_non_ea17_brake_and_start_match_example_span_and_axle_loads(name):
    result = calculate_reactions(parse_reaction_input(example_train_input(name)))
    # Example: Lv=20 m, axle=160 kN, whole girder lengths=20/10 m.
    for side, brake, start in (("B", 160.0, 152.0), ("C", 96.0, 91.2)):
        assert result["longitudinal_base"][side]["length"] == (20 if side == "B" else 10)
        assert result["longitudinal_base"][side]["brake"] == brake
        assert result["longitudinal_base"][side]["start"] == start


@pytest.mark.parametrize("change", ["formation_count", "ultimate_factor"])
def test_non_ea17_braking_does_not_depend_on_formation_or_train_reactions(change):
    data = example_train_input()
    baseline = calculate_reactions(parse_reaction_input(data))
    changed = deepcopy(data)
    train = changed["上部構造"]["列車"]
    if change == "formation_count":
        train["編成数"] = 1
    else:
        train["荷重修正係数"]["安全性(破壊)"] = 0.5
    result = calculate_reactions(parse_reaction_input(changed))
    assert result["train"]["girder"]["ultimate"]["single"] != baseline["train"]["girder"]["ultimate"]["single"]
    for side, brake, start in (("B", 160.0, 152.0), ("C", 96.0, 91.2)):
        assert result["longitudinal_base"][side]["brake"] == baseline["longitudinal_base"][side]["brake"] == brake
        assert result["longitudinal_base"][side]["start"] == baseline["longitudinal_base"][side]["start"] == start


def test_ea17_braking_uses_ultimate_single_track_reaction_total():
    data = example_train_input("EA-17")
    baseline = calculate_reactions(parse_reaction_input(data))
    data["上部構造"]["列車"]["荷重修正係数"]["安全性(破壊)"] = 0.5
    changed = calculate_reactions(parse_reaction_input(data))
    for result in (baseline, changed):
        reactions = result["train"]["girder"]["ultimate"]["single"]
        for side, supports in (("B", ("RA", "RB")), ("C", ("RC", "RD"))):
            total = sum(reactions[support]["train"] for support in supports)
            assert result["longitudinal_base"][side]["brake"] == round(0.32 * total, 2)
            assert result["longitudinal_base"][side]["start"] == round(0.2975 * total, 2)
            assert changed["longitudinal_base"][side]["brake"] < baseline["longitudinal_base"][side]["brake"]


@pytest.mark.parametrize("name_state", ["missing", None, ""])
def test_absent_or_empty_train_name_uses_non_ea17_rule(name_state):
    data = example_train_input()
    train = data["上部構造"]["列車"]
    if name_state == "missing":
        del train["車両名"]
    else:
        train["車両名"] = name_state
    inputs = parse_reaction_input(data)
    assert getattr(inputs.train, "name", None) == ""
    result = calculate_reactions(inputs)
    for side, brake, start in (("B", 160.0, 152.0), ("C", 96.0, 91.2)):
        assert result["longitudinal_base"][side]["brake"] == brake
        assert result["longitudinal_base"][side]["start"] == start


@pytest.mark.parametrize("name", [17, True, [], {}])
def test_non_string_train_name_is_a_path_qualified_input_error(name):
    with pytest.raises(InputError, match=r"上部構造\.列車\.車両名"):
        parse_reaction_input(example_train_input(name))


SNOW_KEYS = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
POINT_DEAD = {"A": (101.0, 17.0), "B": (203.0, 31.0), "C": (307.0, 43.0), "D": (409.0, 59.0)}
POINT_SNOW = {"A": (7.0, 11.0, 13.0), "B": (17.0, 19.0, 23.0),
              "C": (29.0, 31.0, 37.0), "D": (41.0, 43.0, 47.0)}


def asymmetric_snow_input():
    data = example_train_input()
    data["上部構造"]["列車"]["荷重修正係数"]["安全性(破壊)"] = 1.23
    for side, local, remote in (("起点側", "B", "A"), ("終点側", "C", "D")):
        reactions = data["上部工反力"][side]
        for index, row in enumerate(reactions[f"{local}支点"]["支承"]):
            d1, d2 = POINT_DEAD[local] if index == 0 else (0.0, 0.0)
            row.update(固定死荷重_D1=d1, 付加死荷重_D2=d2)
            row.update(dict(zip(SNOW_KEYS, POINT_SNOW[local] if index == 0 else (0.0,) * 3)))
        reactions.setdefault(f"{remote}支点", {})["合計"] = {
            "固定死荷重_D1": POINT_DEAD[remote][0], "付加死荷重_D2": POINT_DEAD[remote][1],
            **dict(zip(SNOW_KEYS, POINT_SNOW[remote])),
        }
    return data


def test_non_ea17_applied_braking_applies_ultimate_factor_once():
    data = asymmetric_snow_input()
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        for index, row in enumerate(data["上部工反力"][side][point]["支承"]):
            row["列車分担"].update(L1=1.0 if index == 0 else 0.0, L2=1.0 if index == 0 else 0.0)
    result = calculate_reactions(parse_reaction_input(data))
    for side, brake in (("B", 160.0), ("C", 96.0)):
        base = result["longitudinal_base"][side]
        assert base["brake"] == brake
        assert base["LR"] == (400.0 if side == "B" else 200.0)
        expected = {4: base["LR"] + 1.23 * brake, 5: 1.1 * base["LR"] + 1.23 * brake,
                    6: base["LR"] + 1.35 * brake, 7: base["LR"] + 1.23 * brake}
        for index, applied in expected.items():
            assert result["longitudinal"][index][side]["applied"] == pytest.approx(applied)
    assert result["longitudinal"][6]["B"]["applied"] == 616.0
    assert result["longitudinal"][6]["C"]["applied"] == pytest.approx(329.6)


@pytest.mark.parametrize("ultimate_factor", [1.0, 0.5])
def test_ea17_applied_braking_does_not_repeat_ultimate_factor(ultimate_factor):
    data = example_train_input("EA-17")
    data["上部構造"]["列車"]["荷重修正係数"]["安全性(破壊)"] = ultimate_factor
    result = calculate_reactions(parse_reaction_input(data))
    for side in ("B", "C"):
        base = result["longitudinal_base"][side]
        for index, lr_factor, brake_factor in ((4, 1.0, 1.0), (5, 1.1, 1.0), (6, 1.0, 1.1), (7, 1.0, 1.0)):
            assert result["longitudinal"][index][side]["applied"] == pytest.approx(
                lr_factor * base["LR"] + brake_factor * max(base["brake"], base["start"]))


# D1, D2, train group, train multiplier, impact multiplier, snow probability.
# Combinations use raw reactions and unrounded impact contributions.
VERTICAL_COMBINATIONS = (
    (1.0, 1.0, None, 0.0, 0.0, 0),
    (1.0, 1.0, "service", 1.0, 1.0, 0),
    (1.1, 1.2, "ultimate", 1.1, 1.1, 1),
    (1.1, 1.2, "ultimate", 1.0, 1.0, 1),
    (1.1, 1.2, "ultimate", 1.1, 1.1, 1),
    (1.1, 1.2, "ultimate", 1.0, 1.0, 1),
    (1.1, 1.2, "ultimate", 1.0, 1.0, 1),
    (1.0, 1.0, "ultimate", 1.0, 1.0, 1),
)


@pytest.mark.parametrize("case_index,combination", tuple(enumerate(VERTICAL_COMBINATIONS)))
def test_bearing_verticals_follow_example_combinations_at_all_four_points(case_index, combination):
    result = calculate_reactions(parse_reaction_input(asymmetric_snow_input()))
    d1_factor, d2_factor, group, train_factor, impact_factor, snow_index = combination
    for side, point, field in (("B", "A", "remote_vertical"), ("B", "B", "local_vertical"),
                               ("C", "D", "remote_vertical"), ("C", "C", "local_vertical")):
        d1, d2 = POINT_DEAD[point]
        expected = d1_factor * d1 + d2_factor * d2 + POINT_SNOW[point][snow_index]
        if group:
            live = result["train"]["girder"][group]["double"][f"R{point}"]
            effective_train = train_factor
            if group == "ultimate":
                # Example rounds the combined rho*gamma coefficient first:
                # 1.23*1.1 -> 1.35, not 1.353. Train tables retain full rho.
                effective_train = 1.35 if train_factor == 1.1 else 1.23
            raw = result["moving_train"]["reactions"][("A", "B", "C", "D").index(point)]
            tracks = result["dead_loads"]["track_totals"][side]
            impact = live["coefficient"] if impact_factor else 0
            expected += effective_train * raw * tracks * (1 + impact)
        assert result["longitudinal"][case_index][side][field] == pytest.approx(expected)


@pytest.mark.parametrize("name", ["EA-17", "EC-16"])
@pytest.mark.parametrize("ultimate_factor", [1.23, 1.231])
def test_combination_coefficients_round_before_applying_without_rounding_train_tables(name, ultimate_factor):
    data = asymmetric_snow_input()
    data["上部構造"]["列車"].update(車両名=name)
    data["上部構造"]["列車"]["荷重修正係数"]["安全性(破壊)"] = ultimate_factor
    inputs = parse_reaction_input(data)
    result = calculate_reactions(inputs)
    assert inputs.train.factors_ultimate == ultimate_factor
    assert result["input"]["train"]["factors_ultimate"] == ultimate_factor
    for index, support in enumerate(("RA", "RB", "RC", "RD")):
        assert result["train"]["girder"]["ultimate"]["single"][support]["train"] == (
            result["moving_train"]["reactions"][index] * ultimate_factor)
    for side, base_brake in (("B", 160.0), ("C", 96.0)):
        base = result["longitudinal_base"][side]
        if name == "EA-17":
            uncorrected_braking = base["braking"] / ultimate_factor
        else:
            assert base["brake"] == base_brake
            uncorrected_braking = base["braking"]
        for index, effective_factor in ((4, 1.23), (6, 1.35)):
            assert result["longitudinal"][index][side]["applied"] == pytest.approx(
                base["LR"] + effective_factor * uncorrected_braking)
        for index, effective_factor in ((4, 1.35), (5, 1.23)):
            live = result["train"]["girder"]["ultimate"]["double"][f"R{side}"]
            raw = result["moving_train"]["reactions"][1 if side == "B" else 2]
            expected = (1.1 * POINT_DEAD[side][0] + 1.2 * POINT_DEAD[side][1] + POINT_SNOW[side][1]
                        + effective_factor * raw * result["dead_loads"]["track_totals"][side] * (1 + live["coefficient"]))
            assert result["longitudinal"][index][side]["local_vertical"] == pytest.approx(expected)


@pytest.mark.parametrize("name", ["EA-17", "EC-16"])
def test_zero_ultimate_factor_has_no_train_or_design_braking_contribution(name):
    data = asymmetric_snow_input()
    data["上部構造"]["列車"].update(車両名=name)
    data["上部構造"]["列車"]["荷重修正係数"]["安全性(破壊)"] = 0.0
    result = calculate_reactions(parse_reaction_input(data))
    for live in result["train"]["girder"]["ultimate"]["double"].values():
        assert live["train"] == live["impact"] == 0.0
    for side, base_brake in (("B", 160.0), ("C", 96.0)):
        base = result["longitudinal_base"][side]
        assert base["brake"] == (0.0 if name == "EA-17" else base_brake)
        for index in (4, 6):
            assert result["longitudinal"][index][side]["applied"] == base["LR"]
        expected = 1.1 * POINT_DEAD[side][0] + 1.2 * POINT_DEAD[side][1] + POINT_SNOW[side][1]
        assert result["longitudinal"][4][side]["local_vertical"] == pytest.approx(expected)
    json.dumps(result, ensure_ascii=False, allow_nan=False)


def test_earthquake_girder_forces_include_only_s2_and_preserve_heights():
    data = asymmetric_snow_input()
    inputs = parse_reaction_input(data)
    result = calculate_reactions(inputs)
    # B is fixed: (118+234)+(7+17)=376. C is movable: ((350+468)+(29+41))/2=444.
    assert result["longitudinal"][8]["B"]["applied"] == 376.0
    assert result["longitudinal"][8]["B"]["force"] == 376.0
    assert result["longitudinal"][8]["C"]["applied"] == 888.0
    assert result["longitudinal"][8]["C"]["force"] == 444.0
    assert result["transverse"][6]["B"]["force"] == 251.0
    assert result["transverse"][6]["C"]["force"] == 379.0
    assert result["transverse"][6]["B"]["height"] == inputs.spans.b.hs
    assert result["transverse"][6]["C"]["height"] == inputs.spans.c.hs
    for side, local, remote in (("起点側", "B", "A"), ("終点側", "C", "D")):
        points = data["上部工反力"][side]
        for target in [*points[f"{local}支点"]["支承"], points[f"{remote}支点"]["合計"]]:
            target[SNOW_KEYS[1]] = 1000.0
            target[SNOW_KEYS[2]] = 2000.0
    changed = calculate_reactions(parse_reaction_input(data))
    assert changed["longitudinal"][8] == result["longitudinal"][8]
    assert changed["transverse"][6] == result["transverse"][6]
    assert changed["longitudinal"][9] == result["longitudinal"][9]
    assert changed["transverse"][7] == result["transverse"][7]


def rounded_force(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def single_precision(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def test_s30_lr_cases_use_dead_and_snow_only_and_have_separate_single_handoff():
    inputs = parse_reaction_input(asymmetric_snow_input())
    result = calculate_reactions(inputs)
    extra = result.get("longitudinal_snow_cases", [])
    assert [row["id"] for row in extra] == ["safety_lr_s30", "recovery_lr_s30"]
    for row, d1_factor, d2_factor in zip(extra, (1.1, 1.0), (1.2, 1.0)):
        assert row["label"]
        for side, remote, span in (("B", "A", inputs.spans.b), ("C", "D", inputs.spans.c)):
            detail = row[side]
            applied = result["longitudinal_base"][side]["LR"]
            remote_vertical = d1_factor * POINT_DEAD[remote][0] + d2_factor * POINT_DEAD[remote][1] + POINT_SNOW[remote][2]
            local_vertical = d1_factor * POINT_DEAD[side][0] + d2_factor * POINT_DEAD[side][1] + POINT_SNOW[side][2]
            assert detail["applied"] == applied
            assert detail["remote_vertical"] == pytest.approx(remote_vertical)
            assert detail["local_vertical"] == pytest.approx(local_vertical)
            if span.bearing == "固定":
                expected_force = max(rounded_force(applied - 0.5 * span.mu * remote_vertical), applied / 2)
            else:
                expected_force = min(applied / 2, max(rounded_force(span.mu * local_vertical), rounded_force(span.mu * applied / 2)))
            assert detail["force"] == expected_force
    assert len(result["longitudinal"]) == 10
    assert [row["case"] for row in result["longitudinal"]] == list(range(1, 11))
    assert [row["source_row"] for row in result["longitudinal"]] == list(range(545, 555))
    handoff = result["macro_handoff_single"]
    assert handoff["線路荷重強度"] == [
        {f"R{side}": single_precision(row[side]["force"]) for side in ("B", "C")}
        for row in result["longitudinal"]
    ]
    assert handoff.get("線路雪荷重強度") == [
        {f"R{side}": single_precision(row[side]["force"]) for side in ("B", "C")}
        for row in extra
    ]


def test_missing_null_and_zero_snow_produce_identical_finite_horizontal_results():
    results = []
    for mode in ("missing", "null", "zero"):
        data = asymmetric_snow_input()
        for side in ("起点側", "終点側"):
            for point in data["上部工反力"][side].values():
                if not isinstance(point, dict):
                    continue
                for row in [*point.get("支承", []), point.get("合計", {})]:
                    for key in SNOW_KEYS:
                        if mode == "missing":
                            row.pop(key, None)
                        else:
                            row[key] = None if mode == "null" else 0.0
        result = calculate_reactions(parse_reaction_input(data))
        assert len(result["longitudinal"]) == 10
        assert len(result.get("longitudinal_snow_cases", [])) == 2
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        results.append(result)
    for key in ("longitudinal", "longitudinal_base", "longitudinal_snow_cases", "transverse", "cells", "macro_handoff_single"):
        assert results[0][key] == results[1][key] == results[2][key]


@pytest.mark.parametrize("end_state", ["missing", "null", "zero"])
def test_end_snow_falls_back_per_probability_but_explicit_zero_is_retained(end_state):
    data = asymmetric_snow_input()
    for side, remote in (("起点側", "A"), ("終点側", "D")):
        total = data["上部工反力"][side][f"{remote}支点"]["合計"]
        for key in SNOW_KEYS:
            if end_state == "missing":
                del total[key]
            else:
                total[key] = None if end_state == "null" else 0.0
    result = calculate_reactions(parse_reaction_input(data))
    for side, remote in (("B", "A"), ("C", "D")):
        expected_snow = POINT_SNOW[side] if end_state != "zero" else (0.0, 0.0, 0.0)
        assert result["snow_loads"]["points"][remote] == dict(zip(SNOW_KEYS, expected_snow))
        assert result["longitudinal"][0][side]["remote_vertical"] == sum(POINT_DEAD[remote]) + expected_snow[0]
        live = result["train"]["girder"]["ultimate"]["double"][f"R{remote}"]
        raw = result["moving_train"]["reactions"][0 if remote == "A" else 3]
        expected_s10 = (sum(POINT_DEAD[remote]) + expected_snow[1]
                        + 1.23 * raw * result["dead_loads"]["track_totals"][side] * (1 + live["coefficient"]))
        assert result["longitudinal"][7][side]["remote_vertical"] == pytest.approx(expected_s10)
        extra = result.get("longitudinal_snow_cases", [])
        assert len(extra) == 2
        assert extra[1][side]["remote_vertical"] == sum(POINT_DEAD[remote]) + expected_snow[2]
