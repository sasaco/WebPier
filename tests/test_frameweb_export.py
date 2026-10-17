"""Independent native-input geometry, load, and rejection contracts."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from src.calculator import calculate
from src.inputs import InputError, parse_input
from src.longitudinal_calculator import calculate_longitudinal
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.frameweb_export import build_frameweb_input, validate_frameweb_input


FIXTURES = Path(__file__).parent / "fixtures"


def canonical_input(*, rho=1.23, service=1, geometry=None, strengths=None):
    data = json.loads((FIXTURES / "frameweb_webpier_reference.json").read_text(encoding="utf-8"))["input"]
    for part, strength in (strengths or {}).items():
        data["鉄筋"][part]["concrete_strength_mpa"] = strength
    inputs = parse_reaction_input(data)
    inputs = replace(inputs, train=replace(inputs.train, factors_ultimate=rho, factors_service=service))
    if geometry:
        inputs = replace(inputs, geometry=replace(inputs.geometry, **geometry))
    return calculate_longitudinal(inputs, calculate(parse_input(data)), calculate_reactions(inputs),
                                  design_conditions=parse_longitudinal_design_conditions(data))


@pytest.fixture(scope="module")
def current_result():
    return canonical_input()


def test_current_webpier_nodes_sections_springs_and_all_basic_actions(current_result):
    reference = json.loads((FIXTURES / "frameweb_webpier_reference.json").read_text(encoding="utf-8"))
    before = deepcopy(current_result)
    exported = build_frameweb_input(current_result)
    native = exported.document
    assert set(native) == {"dimension", "node", "member", "element", "fix_node", "load", "define", "combine", "pickup"}
    assert native["dimension"] == 2
    assert native["node"] == reference["nodes"]
    assert native["member"] == reference["members"]
    for identifier, material in (("1", "beam"), ("2", "column")):
        assert native["element"]["1"][identifier]["E"] == current_result["frame"]["materials"][material]["Ec"]
        assert native["element"]["1"][identifier]["A"] == 12.15
        assert native["element"]["1"][identifier]["Iz"] == 7.38113
    assert native["element"]["1"]["3"]["A"] == native["element"]["1"]["3"]["Iz"] == 1000
    for term, expected in reference["springs"].items():
        row = native["fix_node"][term][0]
        assert [row[key] for key in ("n", "tx", "ty", "rz")] == expected
    for identifier, expected in reference["basic_node_actions"].items():
        rows = native["load"][identifier].get("load_node", [])
        actual = [[row["n"], row.get("tx") or 0, row.get("ty") or 0, row.get("rz") or 0] for row in rows]
        assert actual == expected
    assert native["load"]["1"]["load_member"] == [
        {"m1": str(i), "m2": str(i), "mark": 2, "direction": "gy", "P1": -297.68,
         "P2": -297.68, "L1": 0, "L2": 0, "row": i} for i in (1, 2, 3)]
    assert "load_node" not in native["load"]["5"]
    assert "load_member" not in native["load"]["5"]
    assert exported.source_mapping["zero_load_case_ids"] == [5]
    validate_frameweb_input(json.loads(json.dumps(native, allow_nan=False)))
    assert current_result == before
    assert build_frameweb_input(current_result) == exported


@pytest.mark.parametrize("geometry", [
    {"h1": 0.5, "b1": 2, "b2": 0.5, "b3": 1.0, "b4": 0, "b5": 0, "w3": 2.0},
    {"h1": 0.5, "b1": 2, "b2": 0.75, "b3": 1.0, "b4": 0, "b5": 0, "w3": 2.0},
    {"h2": 0, "h3": 0},
])
def test_supported_geometry_uses_existing_roles_sections_and_load_anchors(geometry):
    from test_frameweb_cases import assert_all_vectors
    source = canonical_input(geometry=geometry, strengths={"梁": 24, "柱": 40})
    native = build_frameweb_input(source).document
    frame = source["frame"]
    assert len(native["node"]) == len(frame["nodes"])
    assert len(native["member"]) == len(frame["members"])
    assert native["element"]["1"]["1"]["E"] != native["element"]["1"]["2"]["E"]
    if geometry.get("h1"):
        assert any(row["region"] == "parapet_arm" for row in frame["members"]) == (geometry["b2"] == 0.75)
    assert [int(row["m1"]) for row in native["load"]["1"]["load_member"]] == frame["load_anchors"]["column_line_load"]["member_ids"]
    for member in frame["members"]:
        if member["region"] == "h1":
            assert native["member"][str(member["id"])]["e"] == "4"
            assert native["element"]["1"]["4"]["E"] == frame["materials"]["column"]["Ec"]
        if member["region"] == "parapet_arm":
            assert native["member"][str(member["id"])]["e"] == "3"
    assert_all_vectors(source, native)


def test_nonsequential_nodes_and_members_preserve_all_references(current_result):
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
    for role in ("cap_top", "footing_centroid"):
        frame["load_anchors"][role]["node_id"] = nodes[frame["load_anchors"][role]["node_id"]]
    line = frame["load_anchors"]["column_line_load"]
    line.update(from_node_id=nodes[line["from_node_id"]], to_node_id=nodes[line["to_node_id"]],
                member_ids=[members[value] for value in line["member_ids"]])
    frame["load_anchors"]["pedestal"]["equivalent_node_id"] = nodes[frame["load_anchors"]["pedestal"]["equivalent_node_id"]]
    native = build_frameweb_input(source).document
    assert set(native["node"]) == {str(value) for value in nodes.values()}
    assert set(native["member"]) == {str(value) for value in members.values()}
    assert [row["m1"] for row in native["load"]["1"]["load_member"]] == ["20", "31", "42"]
    assert native["fix_node"]["1"][0]["n"] == "47"


@pytest.mark.parametrize("path,value", [
    (("schema_version",), 1), (("case_model_version",), "future"), (("frame", "model_version"), 3),
    (("frame", "members", 0, "material_ref"), "column"),
    (("frame", "members", 0, "section_ref"), "unknown"),
    (("frame", "members", 0, "node_j"), 999),
    (("frame", "nodes", 4, "y"), 10.3),
    (("frame", "nodes", 0, "x"), float("nan")),
    (("frame", "materials", "column", "Ec"), float("inf")),
    (("frame", "materials", "beam", "Ec"), 0),
    (("frame", "load_anchors", "cap_top", "node_id"), 3),
    (("frame", "load_anchors", "column_line_load", "member_ids"), [1, 2, 4]),
    (("frame", "load_anchors", "pedestal", "automatic_self_weight"), True),
    (("frame", "spring_provenance", "support_node_id"), 3),
    (("frame", "spring_provenance", "components", 0, "value"), 0),
    (("frame", "springs", "long_term", "Ks"), -5),
    (("frame", "springs", "long_term", "Ks"), 1),
    (("frame", "springs", "short_term", "Kr"), 0),
    (("frame", "node_ids", "cap_top"), True),
    (("frame", "members", 0, "node_i"), True),
])
def test_reject_invalid_canonical_contract(current_result, path, value):
    source = deepcopy(current_result)
    target = source
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(InputError):
        build_frameweb_input(source)


@pytest.mark.parametrize("change", ["missing_anchor", "missing_load", "duplicate_member", "missing_member", "missing_role", "extra_section"])
def test_reject_missing_or_unsupported_structure(current_result, change):
    source = deepcopy(current_result)
    frame = source["frame"]
    if change == "missing_anchor":
        del frame["load_anchors"]["footing_centroid"]
    elif change == "missing_load":
        del source["basic_cases"][0]["loads"]["column"]
    elif change == "duplicate_member":
        frame["members"].append(deepcopy(frame["members"][0]))
    elif change == "missing_member":
        frame["members"].pop()
    elif change == "missing_role":
        del frame["node_ids"]["footing_top"]
    else:
        frame["sections"]["new"] = deepcopy(frame["sections"]["body"])
    with pytest.raises(InputError):
        build_frameweb_input(source)


@pytest.mark.parametrize("change", ["unknown_top", "missing_load", "missing_node", "bad_member", "fixed_one", "double_impact", "aux_factor", "pickup_duplicate", "wrong_spring"])
def test_native_reload_validation_rejects_bad_references_and_semantics(current_result, change):
    native = build_frameweb_input(current_result).document
    if change == "unknown_top":
        native["provenance"] = {}
    elif change == "missing_load":
        del native["load"]["5"]
    elif change == "missing_node":
        del native["node"]["1"]
    elif change == "bad_member":
        native["member"]["1"]["e"] = "99"
    elif change == "fixed_one":
        native["fix_node"]["1"][0]["tx"] = 1
    elif change == "double_impact":
        native["combine"]["1"]["C12"] = 1.35
    elif change == "aux_factor":
        native["combine"]["1"]["C28"] = 1.35
    elif change == "pickup_duplicate":
        native["pickup"]["1"]["C2"] = 1
    else:
        native["load"]["14"]["fix_node"] = 2
    with pytest.raises(InputError):
        validate_frameweb_input(native)


def test_reject_distributed_load_precision_lost_by_solver_projection(current_result):
    source = deepcopy(current_result)
    source["basic_cases"][0]["loads"]["column"]["intensity"] = 297.681
    for combination in source["combinations"]:
        factor = combination["coefficients"][0]
        combination["resolved_components"][0]["loads"]["column"]["intensity"] = 297.681 * factor
        for variant in combination["variants"]:
            variant["resolved_components"][0]["loads"]["column"]["intensity"] = 297.681 * factor
    with pytest.raises(InputError, match="投影.*丸め"):
        build_frameweb_input(source)


@pytest.mark.parametrize("target", ["root", "roles", "sections", "load", "node"])
def test_malformed_containers_report_input_error(current_result, target):
    if target in ("root", "roles", "sections"):
        source = deepcopy(current_result)
        if target == "root":
            source = []
        elif target == "roles":
            source["frame"]["node_ids"] = []
        else:
            source["frame"]["sections"] = ["body"]
        with pytest.raises(InputError):
            build_frameweb_input(source)
    else:
        native = build_frameweb_input(current_result).document
        # Matching IDs alone must not let a list pass as a native table.
        native[target] = list(native[target])
        with pytest.raises(InputError):
            validate_frameweb_input(native)
