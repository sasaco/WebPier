"""Independent physical expectations for the transverse native adapter."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from src.calculator import calculate
from src.inputs import InputError, parse_input
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.transverse_calculator import calculate_transverse
from src.frameweb_export import build_frameweb_input, validate_frameweb_input


FIXTURES = Path(__file__).parent / "fixtures"


def canonical_input(*, rho=None, service=None, geometry=None, strengths=None, epsilon=None):
    data = json.loads((FIXTURES / "frameweb_webpier_reference.json").read_text(encoding="utf-8"))["input"]
    for part, strength in (strengths or {}).items():
        data["鉄筋"][part]["concrete_strength_mpa"] = strength
    inputs = parse_reaction_input(data)
    inputs = replace(inputs, train=replace(inputs.train,
        factors_ultimate=inputs.train.factors_ultimate if rho is None else rho,
        factors_service=inputs.train.factors_service if service is None else service))
    if geometry:
        inputs = replace(inputs, geometry=replace(inputs.geometry, **geometry))
    if epsilon is not None:
        b = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.b)
        c = tuple(replace(row, factors=(0, 0, 0, 0)) for row in inputs.dead.c)
        c = (replace(c[0], factors=(.1, -.5, 0, 0), position=-2),
             replace(c[1], factors=(.2, .5 + epsilon, 0, 0), position=5), *c[2:])
        inputs = replace(inputs, dead=replace(inputs.dead, b=b, c=c))
    return calculate_transverse(inputs, calculate(parse_input(data)), calculate_reactions(inputs),
                                design_conditions=parse_longitudinal_design_conditions(data))


@pytest.fixture(scope="module")
def current_result():
    return canonical_input()


def test_current_webpier_native_geometry_actions_and_no_mutation(current_result):
    reference = json.loads((FIXTURES / "frameweb_transverse_webpier_reference.json").read_text(encoding="utf-8"))
    before = deepcopy(current_result)
    export = build_frameweb_input(current_result)
    native = export.document
    assert [len(native[key]) for key in ("load", "define", "combine", "pickup")] == [22, 19, 16, 8]
    assert "stage" not in native
    assert native["node"] == reference["nodes"]
    for key in ("1", "2"):
        assert native["element"]["1"][key]["Iz"] == 20.50313
        assert native["element"]["1"][key]["A"] == 12.15
    assert [native["fix_node"][key][0]["rz"] for key in ("1", "2")] == [86320647, 172641294]
    assert [[native["fix_node"][key][0][axis] for axis in ("n", "tx", "ty", "rz")] for key in ("1", "2")] == [
        ["4", 4262769, 12788244, 86320647], ["4", 8525475, 25576488, 172641294]]
    assert [[int(row[axis]) for axis in ("ni", "nj", "e")] for row in native["member"].values()] == [
        [1,5,1], [5,6,1], [6,2,2], [2,3,3], [3,4,3]]
    for identifier, expected in reference["basic_node_actions"].items():
        actual = [[row["n"], row["tx"] or 0, row["ty"] or 0, row["rz"] or 0]
                  for row in native["load"][identifier].get("load_node", [])]
        assert actual == expected
    for identifier, direction, q in (("1", "gy", -297.68), ("16", "gx", 4.050000000000001), ("17", "gx", 8.100000000000001)):
        assert native["load"][identifier]["load_member"] == [
            {"m1": str(i), "m2": str(i), "mark": 2, "direction": direction,
             "P1": q, "P2": q, "L1": 0, "L2": 0, "row": i} for i in (1, 2, 3)]
    assert export.source_mapping["zero_load_case_ids"] == [5]
    assert export.source_mapping["verified_variant_count"] == 37
    validate_frameweb_input(json.loads(json.dumps(native)), stage="0620")
    assert current_result == before
    assert build_frameweb_input(current_result) == export


def test_resolved_helpers_use_usage_values_and_leave_d1_factor_after_projection(current_result):
    exported = build_frameweb_input(current_result)
    native = exported.document
    for identifier, force, moment in ((18, 1975.64, 0), (19, 1800.07, 0), (20, 1380.07, 0),
                                      (21, 695.89, 1482.81), (22, 695.89, -1482.81)):
        row = native["load"][str(identifier)]["load_node"][0]
        assert row["ty"] == pytest.approx(-force, abs=1e-10)
        assert (row["rz"] or 0) == pytest.approx(-moment, abs=1e-10)
        assert native["load"][str(identifier)]["fix_node"] == 2
    assert native["define"]["19"] == {"row": 19, "C1": 21, "C2": 22}
    q = native["load"]["1"]["load_member"][0]["P1"]
    assert -q * native["combine"]["1"]["C1"] == pytest.approx(327.448)
    assert round(-q * native["combine"]["1"]["C1"], 2) == 327.45
    assert len(exported.source_mapping["auxiliary_cases"]) == 5


@pytest.mark.parametrize("change", ["action_units", "unknown_point_component", "line_extent", "effective_factor", "wrong_helper"])
def test_reject_silent_semantic_changes(current_result, change):
    source = deepcopy(current_result)
    if change == "wrong_helper":
        native = build_frameweb_input(source).document
        native["combine"]["7"] = {"row": 7, "name": "bad", "C16": 1}
        with pytest.raises(InputError):
            validate_frameweb_input(native, stage="0620")
        return
    if change == "action_units":
        source["basic_cases"][0]["loads"]["units"]["N"] = "N"
    elif change == "unknown_point_component":
        source["basic_cases"][0]["loads"]["points"][0]["torsion"] = 10
    elif change == "line_extent":
        source["basic_cases"][0]["loads"]["line_loads"][0]["L2"] = 1.08
    else:
        for combination in source["combinations"]:
            for component in combination["resolved_components"]:
                for candidate in component["candidates"]:
                    if candidate["action_key"].startswith("impact_"):
                        candidate["loads"]["details"]["effective_factor"] = 99
    with pytest.raises(InputError):
        build_frameweb_input(source)


@pytest.mark.parametrize("geometry", [
    {"h1": .5, "w1": 2, "w2": .5, "w3": 1, "w4": 0, "w5": 0, "b3": 2},
    {"h1": .5, "w1": 2, "w2": .75, "w3": 1, "w4": 0, "w5": 0, "b3": 2},
    {"h2": 0, "h3": 0},
])
def test_h1_zero_length_merging_and_separate_materials(geometry):
    from test_frameweb_transverse_cases import assert_states
    source = canonical_input(geometry=geometry, strengths={"梁": 24, "柱": 40})
    native = build_frameweb_input(source).document
    frame = source["frame"]
    assert len(native["node"]) == len(frame["nodes"])
    assert len(native["member"]) == len(frame["members"])
    assert native["element"]["1"]["1"]["E"] != native["element"]["1"]["2"]["E"]
    for case in ("1", "16", "17"):
        assert [int(row["m1"]) for row in native["load"][case]["load_member"]] == frame["load_anchors"]["column_line_load"]["member_ids"]
    if geometry.get("h1"):
        assert native["element"]["1"]["4"]["E"] == frame["materials"]["column"]["Ec"]
        assert any(row["region"] == "parapet_arm" for row in frame["members"]) == (geometry["w2"] == .75)
    assert_states(source, native)


def test_nonsequential_ids_preserve_every_physical_anchor(current_result):
    source = deepcopy(current_result)
    frame = source["frame"]
    nodes = {row["id"]: 10 * row["id"] + 7 for row in frame["nodes"]}
    members = {row["id"]: 11 * row["id"] + 9 for row in frame["members"]}
    for row in frame["nodes"]:
        row["id"] = nodes[row["id"]]
    for row in frame["members"]:
        row.update(id=members[row["id"]], node_i=nodes[row["node_i"]], node_j=nodes[row["node_j"]])
    frame["node_ids"] = {key: nodes[value] for key, value in frame["node_ids"].items()}
    frame["support_node_id"] = frame["spring_provenance"]["support_node_id"] = nodes[frame["support_node_id"]]
    for anchor in ("cap_top", "footing_centroid"):
        frame["load_anchors"][anchor]["node_id"] = nodes[frame["load_anchors"][anchor]["node_id"]]
    line = frame["load_anchors"]["column_line_load"]
    line.update(from_node_id=nodes[line["from_node_id"]], to_node_id=nodes[line["to_node_id"]],
                member_ids=[members[i] for i in line["member_ids"]])
    frame["load_anchors"]["pedestal"]["equivalent_node_id"] = nodes[frame["load_anchors"]["pedestal"]["equivalent_node_id"]]
    # Basic loads and actions share objects; update each physical object once.
    seen = set()
    actions = list(source["actions"].values()) + [candidate["loads"] for c in source["combinations"]
               for component in c["resolved_components"] for candidate in component["candidates"]]
    for action in actions:
        if id(action) in seen:
            continue
        seen.add(id(action))
        for point in action["points"]:
            point["node_id"] = nodes[point["node_id"]]
        for line in action["line_loads"]:
            line.update(from_node_id=nodes[line["from_node_id"]], to_node_id=nodes[line["to_node_id"]],
                        member_ids=[members[i] for i in line["member_ids"]])
    native = build_frameweb_input(source).document
    assert set(native["node"]) == {str(i) for i in nodes.values()}
    assert [row["m1"] for row in native["load"]["16"]["load_member"]] == ["20", "31", "42"]
    assert native["load"]["15"]["load_node"][0]["n"] == "17"


def test_unknown_distributed_projection_loss_is_rejected_with_values(current_result):
    source = deepcopy(current_result)
    source["actions"]["dead_fixed"]["line_loads"][0]["qN"] = 297.681
    for combination in source["combinations"]:
        for component in combination["resolved_components"]:
            if component["define_case_id"] == 1:
                component["candidates"][0]["loads"]["line_loads"][0]["qN"] = 297.681 * component["nominal_coefficient"]
    with pytest.raises(InputError, match="投影.*297.681.*297.68"):
        build_frameweb_input(source)


def test_projection_must_not_turn_a_nonzero_row_into_a_skipped_zero_row(current_result):
    native = build_frameweb_input(current_result).document
    # Smaller than numeric tolerance, but projection changes case availability.
    row = native["load"]["16"]["load_member"][0]
    row["P1"] = row["P2"] = 1e-11
    with pytest.raises(InputError, match="投影.*0"):
        validate_frameweb_input(native, stage="0620")


@pytest.mark.parametrize("change", ["negative_member", "wrong_spring", "vertical_in_sign_case", "factor_twice", "unknown_axis", "extra_3d", "bool_id"])
def test_native_transverse_profile_rejects_invalid_semantics(current_result, change):
    native = build_frameweb_input(current_result).document
    if change == "negative_member":
        native["load"]["16"]["load_member"][0]["m2"] = "-3"
    elif change == "wrong_spring":
        native["load"]["15"]["fix_node"] = 1
    elif change == "vertical_in_sign_case":
        native["load"]["15"]["load_node"][0]["ty"] = 100
    elif change == "factor_twice":
        native["combine"]["1"]["C16"] = 1.35
    elif change == "unknown_axis":
        native["load"]["16"]["load_member"][0]["direction"] = "x"
    elif change == "extra_3d":
        native["load"]["15"]["load_node"][0]["tz"] = 100
    else:
        native["define"]["1"]["C1"] = True
    with pytest.raises(InputError):
        validate_frameweb_input(native, stage="0620")
