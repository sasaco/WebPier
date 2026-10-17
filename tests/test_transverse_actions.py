"""Independent physical checks for the Example2 transverse action contract."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from src.calculator import calculate, vba_single
from src.inputs import InputError, parse_input
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.transverse_actions import build_transverse_actions, impact_action, train_action
from src.transverse_calculator import calculate_transverse, calculate_transverse_legacy


@pytest.fixture(scope="module")
def current():
    data = json.loads((Path(__file__).parents[1] / "pre" / "input.json").read_text(encoding="utf-8-sig"))
    inputs = parse_reaction_input(data)
    foundation = calculate(parse_input(data))
    reactions = calculate_reactions(inputs)
    conditions = parse_longitudinal_design_conditions(data)
    result = calculate_transverse(inputs, foundation, reactions, design_conditions=conditions)
    return data, inputs, foundation, reactions, conditions, result


def test_current_dead_actions_keep_application_points_and_cancel_symmetry(current):
    result = current[-1]
    fixed = result["actions"]["dead_fixed"]
    additional = result["actions"]["dead_additional"]
    assert fixed["table_totals"] == {"anchor": "cap_top", "N": 8299.52, "H": 0, "M": 0}
    assert [(row["anchor"], row["N"]) for row in fixed["points"]] == [
        ("cap_top", 8299.52), ("footing_centroid", vba_single(4167.45))]
    assert fixed["line_loads"][0]["qN"] == 297.68
    assert fixed["line_loads"][0]["unit"] == "kN/m"
    assert fixed["line_loads"][0]["from_node_id"] == result["frame"]["node_ids"]["cap_top"]
    assert additional["table_totals"]["N"] == 780
    assert additional["table_totals"]["M"] == 0
    assert additional["points"][1]["N"] == vba_single(1830.60)


def test_current_train_has_both_tracks_correct_arms_and_single_distribution(current):
    actions = current[-1]["actions"]
    for name, moment in (("train_up", 1210.08), ("train_down", -1210.08), ("train_double", 0)):
        action = actions[name]
        assert action["table_totals"]["N"] == (1134.77 if name.endswith("double") else 567.39)
        assert action["table_totals"]["M"] == moment
        c_rows = [row for row in action["rows"] if row["side"] == "C"]
        assert [row["arm"] for row in c_rows[:2]] == [-2.95, 2.95]
        assert all(row["N"] == row["M"] == 0 for row in c_rows[2:])
    assert "single_track_selection" not in current[-1]


def test_non_symmetric_c_moment_uses_own_position(current):
    _, inputs, _, reactions, _, result = current
    bearings = tuple(replace(b, d1=0, d2=0) for b in inputs.dead.b)
    c_bearings = tuple(replace(b, d1=0, d2=0) for b in inputs.dead.c)
    c_bearings = (replace(c_bearings[0], d1=123, position=6), *c_bearings[1:])
    changed = replace(inputs, dead=replace(inputs.dead, b=bearings, c=c_bearings))
    action = build_transverse_actions(changed, reactions, frame=result["frame"])["dead_fixed"]
    assert action["table_totals"]["M"] == 738


def test_all_snow_probabilities_are_real_actions(current):
    actions = current[-1]["actions"]
    for period, value in ((2, 710), (10, 1140), (30, 1270)):
        assert actions[f"snow_{period}_year"]["table_totals"] == {
            "anchor": "cap_top", "N": value, "H": 0, "M": 0}


def test_impact_matches_upstream_only_at_its_original_factor_without_double_application(current):
    _, inputs, _, reactions, _, result = current
    for usage in ("ultimate", "service"):
        factor = getattr(inputs.train, f"factors_{usage}")
        for track, upstream_track in (("up", "single"), ("double", "double")):
            action = impact_action(inputs, reactions, result["frame"], track, usage, factor)
            for side, support in zip(action["details"]["sides"], ("RB", "RC")):
                upstream = reactions["train"]["pier"][usage][upstream_track][support]
                assert side["impact_total"] == vba_single(upstream["impact"])
                assert side["impact_coefficient"] == upstream["coefficient"]
    ordinary = impact_action(inputs, reactions, result["frame"], "double", "ultimate", 1.23)
    assert [round(side["impact_total"], 1) for side in ordinary["details"]["sides"]] == [114.2, 290.1]


def test_signed_zero_rate_sum_preserves_moment_and_never_divides_by_zero(current):
    _, inputs, _, reactions, _, result = current
    b = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.b)
    c = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.c)
    c = (replace(c[0], factors=(0, -0.5, 0, 0)), replace(c[1], factors=(0, 0.5, 0, 0)), *c[2:])
    changed = replace(inputs, dead=replace(inputs.dead, b=b, c=c))
    action = impact_action(changed, reactions, result["frame"], "up", "ultimate", 1)
    assert action["table_totals"]["N"] == 0
    assert action["table_totals"]["M"] > 0
    assert action["details"]["sides"][1]["zero_sum_signed_rates"] is True


def test_missing_loaded_position_is_not_silently_replaced(current):
    _, inputs, _, reactions, _, result = current
    c = (replace(inputs.dead.c[0], position=None), *inputs.dead.c[1:])
    changed = replace(inputs, dead=replace(inputs.dead, c=c))
    with pytest.raises(InputError, match="position"):
        train_action(changed, reactions, result["frame"], "up")


def test_wind_preserves_existing_loads_exactly(current):
    _, inputs, foundation, reactions, _, result = current
    old = calculate_transverse_legacy(inputs, foundation, reactions)
    for index, key in ((1, "wind_with_train"), (2, "wind_without_train")):
        assert result["actions"][key]["table_totals"]["H"] == old["horizontal_aggregates"][index]["H"]
        assert result["actions"][key]["table_totals"]["M"] == old["horizontal_aggregates"][index]["M"]


def test_material_part_inputs_and_exact_transverse_springs(current):
    data, inputs, foundation, reactions, _, original = current
    data = deepcopy(data)
    for part, strength in (("梁", 30), ("柱", 24), ("フーチング", 18)):
        data["鉄筋"][part]["concrete_strength_mpa"] = strength
    result = calculate_transverse(inputs, foundation, reactions,
                                  design_conditions=parse_longitudinal_design_conditions(data))
    frame = result["frame"]
    assert {key: value["Ec"] for key, value in frame["materials"].items()} == {
        "beam": 28e6, "column": 25e6, "footing": 22e6}
    assert {row["region"]: row["material_ref"] for row in frame["members"]} == {
        "h2": "beam", "h3": "beam", "h4": "column",
        "footing_top_to_centroid": None, "footing_centroid_to_bottom": None}
    assert frame["nodes"] == original["frame"]["nodes"]
    assert frame["sections"] == original["frame"]["sections"]
    assert frame["springs"]["long_term"]["Kr"] == foundation["long_term"]["Kr_transverse"]


def test_resolved_cases_are_alternatives_and_factor_once(current):
    result = current[-1]
    assert len(result["actions"]) == len(result["basic_cases"]) == 17
    combo = result["combinations"][0]
    by_define = {item["define_case_id"]: item for item in combo["resolved_components"]}
    train = by_define[10]["candidates"][0]
    assert train["loads"]["table_totals"]["N"] == 1531.94
    assert train["coefficient_trace"]["effective_factor"] == 1.35
    assert train["coefficient_trace"]["remaining_multiplier"] == 1
    positive, negative = by_define[13]["candidates"]
    assert positive["loads"]["table_totals"]["N"] == negative["loads"]["table_totals"]["N"] == 0
    assert positive["loads"]["table_totals"]["H"] == -negative["loads"]["table_totals"]["H"]
    assert positive["loads"]["table_totals"]["H"] == pytest.approx(111.69 * 1.23)
    assert result["actions"]["vehicle_lateral"]["table_totals"]["M"] == 430.01
    service = result["combinations"][6]["resolved_components"]
    assert [[candidate["direction"] for candidate in component["candidates"]] for component in service] == [
        ["up", "down"], ["up", "down"]]
    impact = service[1]["candidates"][0]
    assert impact["coefficient_trace"]["nominal_coefficient"] == .75
    assert impact["coefficient_trace"]["effective_factor"] == 1


def test_zero_ultimate_factor_does_not_require_dividing_upstream_lateral(current):
    _, inputs, foundation, reactions, conditions, result = current
    inputs = replace(inputs, train=replace(inputs.train, factors_ultimate=0))
    actions = build_transverse_actions(inputs, reactions, frame=result["frame"])
    assert actions["vehicle_lateral"]["table_totals"]["H"] == 111.69
    calculated = calculate_transverse(inputs, foundation, calculate_reactions(inputs), design_conditions=conditions)
    assert all(component["define_case_id"] not in (9, 10, 11, 12, 13)
               for component in calculated["combinations"][0]["resolved_components"])


def test_nonstandard_service_factor_is_applied_once_to_train_and_impact(current):
    _, inputs, foundation, _, conditions, _ = current
    inputs = replace(inputs, train=replace(inputs.train, factors_service=1.4))
    reactions = calculate_reactions(inputs)
    result = calculate_transverse(inputs, foundation, reactions, design_conditions=conditions)
    components = {row["define_case_id"]: row for row in result["combinations"][4]["resolved_components"]}
    train, impact = components[10]["candidates"][0], components[12]["candidates"][0]
    assert train["coefficient_trace"]["effective_factor"] == 1.4
    assert impact["coefficient_trace"]["nominal_coefficient"] == pytest.approx(1.05, abs=1e-14)
    assert impact["coefficient_trace"]["effective_factor"] == 1.4
    for row, support in zip(impact["loads"]["details"]["sides"], ("RB", "RC")):
        assert row["impact_total"] == vba_single(reactions["train"]["pier"]["service"]["double"][support]["impact"])


def test_nonzero_h1_preserves_section_and_uses_column_material(current):
    _, inputs, foundation, reactions, conditions, _ = current
    inputs = replace(inputs, geometry=replace(inputs.geometry, h1=.3, b3=.5, w3=.7))
    result = calculate_transverse(inputs, foundation, reactions, design_conditions=conditions)
    h1 = next(row for row in result["frame"]["members"] if row["region"] == "h1")
    assert h1["section_ref"] == "parapet"
    assert h1["material_ref"] == "column"
    assert all(row["material_ref"] is None for row in result["frame"]["members"] if row["behavior"] == "rigid")


def test_report_presence_distinguishes_actual_zero_position_from_unused_bearing(current):
    _, inputs, _, reactions, _, result = current
    b = (*inputs.dead.b[:4], replace(inputs.dead.b[4], position=0), *inputs.dead.b[5:])
    inputs = replace(inputs, dead=replace(inputs.dead, b=b))
    actions = build_transverse_actions(inputs, reactions, frame=result["frame"])
    for key in ("dead_fixed", "dead_additional", "snow_2_year", "train_up", "impact_double"):
        fifth, sixth = actions[key]["rows"][4:6]
        assert fifth["active"] is True and fifth["bearing_position"] == 0
        assert sixth["active"] is False and sixth["bearing_position"] is None


@pytest.mark.parametrize("epsilon,expected_N,expected_M", [
    (0, 0, 358.18), (0.00001, 0, 358.18), (0.0001, 0, 358.20),
    (0.0004, 0, 358.32), (0.00042, .1, 358.32),
    (0.0005, .1, 358.35), (0.001, .1, 358.53),
])
def test_nearly_canceling_signed_impact_retains_couple_through_rounding_boundary(
        current, epsilon, expected_N, expected_M):
    _, inputs, _, reactions, _, result = current
    b = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.b)
    c = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.c)
    c = (replace(c[0], factors=(0, -.5, 0, 0)),
         replace(c[1], factors=(0, .5 + epsilon, 0, 0)), *c[2:])
    changed = replace(inputs, dead=replace(inputs.dead, b=b, c=c))
    action = impact_action(changed, reactions, result["frame"], "up", "ultimate", 1)
    assert action["table_totals"]["N"] == expected_N
    assert action["table_totals"]["M"] == expected_M
    rows = action["rows"][10:12]
    k = reactions["train"]["raw_reactions"]["RC"] * reactions["train"]["pier"]["ultimate"]["single"]["RC"]["coefficient"]
    raw = [k * -.5, k * (.5 + epsilon)]
    target = action["details"]["sides"][1]["impact_total"]
    assert sum(row["raw_N"] for row in rows) == pytest.approx(target, abs=1e-12)
    # Only the rounded support-total residual may alter the bearing forces.
    assert sum(abs(row["raw_N"] - force) for row, force in zip(rows, raw)) == pytest.approx(
        abs(target - sum(raw)), abs=1e-12)


def test_current_mixed_sign_impact_rounding_changes_are_explicit(current):
    _, inputs, _, reactions, _, result = current
    assert result["actions"]["impact_up"]["table_totals"]["M"] == 364.43
    assert result["actions"]["impact_down"]["table_totals"]["M"] == -364.43
    service = impact_action(inputs, reactions, result["frame"], "up", "service", 1)
    assert service["table_totals"]["M"] == 272.73


@pytest.mark.parametrize("epsilon,expected_N,expected_M", [(.00049, 0, 350.17), (.00051, .1, 350.33)])
@pytest.mark.parametrize("polarity", [1, -1])
def test_asymmetric_signed_impact_rounding_boundary_in_both_signs(
        current, epsilon, expected_N, expected_M, polarity):
    _, inputs, _, reactions, _, result = current
    reactions = deepcopy(reactions)
    reactions["train"]["raw_reactions"]["RC"] = 100.0
    reactions["train"]["pier"]["ultimate"]["single"]["RC"]["coefficient"] = 1.0
    b = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.b)
    c = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.c)
    c = (replace(c[0], factors=(0, -.5 * polarity, 0, 0), position=-2),
         replace(c[1], factors=(0, (.5 + epsilon) * polarity, 0, 0), position=5), *c[2:])
    inputs = replace(inputs, dead=replace(inputs.dead, b=b, c=c))
    action = impact_action(inputs, reactions, result["frame"], "up", "ultimate", 1)
    assert action["table_totals"]["N"] == expected_N * polarity
    assert action["table_totals"]["M"] == expected_M * polarity
    side = action["details"]["sides"][1]
    assert sum(row["raw_N"] for row in action["rows"][10:12]) == pytest.approx(side["impact_total"], abs=1e-12)


def test_single_sign_impact_distribution_matches_original_proportional_rule(current):
    _, inputs, _, reactions, _, result = current
    action = impact_action(inputs, reactions, result["frame"], "double", "ultimate", 1.23)
    for side, detail in zip(("B", "C"), action["details"]["sides"]):
        for row in (row for row in action["rows"] if row["side"] == side):
            expected = detail["impact_total"] * row["factor"] / detail["rate_sum"]
            assert row["raw_N"] == pytest.approx(expected, abs=1e-12)
