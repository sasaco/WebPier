"""Independent frame-v2 geometry, topology and load-attribution contracts."""

from copy import deepcopy
from dataclasses import asdict
from itertools import product
import json
import math
from pathlib import Path

import pytest

from src.frame_model import build_frame_model, parapet_center
from src.inputs import InputError
from src.reaction_inputs import parse_reaction_input


PROJECT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT / "tests" / "fixtures" / "pier_models"
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = FIXTURES.parent / "baseline_input.json"
EXPECTATIONS = json.loads((FIXTURES / "expectations.json").read_text(encoding="utf-8"))["cases"]


def case_inputs(name, direction):
    case = EXPECTATIONS[name]
    path = FIXTURES / case["input_fixture"] if case["input_fixture"] else BASELINE
    geometry = asdict(parse_reaction_input(json.loads(path.read_text(encoding="utf-8"))).geometry)
    for fields in case["geometry_overrides"].values():
        geometry.update({key.lower(): value for key, value in fields.items()})
    expected = case["directions"][direction]
    # The four original nodes and body sections are independently fixed fixture
    # inputs, not recovered by invoking the production frame builder.
    legacy = {"nodes": [{key: value for key, value in node.items() if key != "active_node_id"}
                        for node in expected["legacy_nodes"]],
              "section": deepcopy(expected["sections"]["body"]),
              "materials": {"body": {"fck": 24 if direction == "b" else 25, "Ec": 2.5e7},
                            "footing": {"fck": 24 if direction == "b" else 25, "Ec": 2.5e7}},
              "springs": {"long_term": {"Kv": 1, "Ks": 2, "Kr": 3},
                          "short_term": {"Kv": 4, "Ks": 5, "Kr": 6}},
              "shape_eccentricity": -0.125}
    return geometry, legacy, expected


def assert_expected_frame(actual, expected):
    assert {key: value for key, value in actual.items() if key in expected and key != "nodes"} == {
        key: value for key, value in expected.items() if key != "nodes"}
    assert len(actual["nodes"]) == len(expected["nodes"])
    for node, fixed in zip(actual["nodes"], expected["nodes"]):
        assert {key: value for key, value in node.items() if key not in ("x", "y")} == {
            key: value for key, value in fixed.items() if key not in ("x", "y")}
        # Height literals differ only by arithmetic association in binary64.
        assert node["y"] == pytest.approx(fixed["y"], rel=0, abs=4e-15)
        assert node["x"] == fixed["x"]  # tiny eccentricities must remain nonzero


def assert_connected(frame):
    nodes = {node["id"]: node for node in frame["nodes"]}
    assert list(nodes) == sorted(nodes)
    assert [member["id"] for member in frame["members"]] == sorted(member["id"] for member in frame["members"])
    assert len({(node["x"], node["y"]) for node in nodes.values()}) == len(nodes)
    adjacency = {identifier: set() for identifier in nodes}
    edges = set()
    for member in frame["members"]:
        start, end = member["node_i"], member["node_j"]
        assert start in nodes and end in nodes and start != end
        assert math.hypot(nodes[start]["x"] - nodes[end]["x"], nodes[start]["y"] - nodes[end]["y"]) > 0
        assert frozenset((start, end)) not in edges
        edges.add(frozenset((start, end)))
        adjacency[start].add(end)
        adjacency[end].add(start)
        if member["behavior"] == "rigid":
            assert member["section_ref"] is None and member["material_ref"] is None
        else:
            assert member["behavior"] == "elastic"
            assert member["section_ref"] in frame["sections"]
            assert member["material_ref"] == "body"
    reached, pending = set(), [frame["support_node_id"]]
    while pending:
        identifier = pending.pop()
        if identifier not in reached:
            reached.add(identifier)
            pending.extend(adjacency[identifier] - reached)
    assert reached == set(nodes)


@pytest.mark.parametrize("name", EXPECTATIONS)
@pytest.mark.parametrize("direction", ("b", "w"))
def test_complete_independent_frame_fixtures(name, direction):
    geometry, legacy, expected = case_inputs(name, direction)
    before = deepcopy(geometry), deepcopy(legacy)
    actual = build_frame_model(geometry, legacy, direction)
    assert_expected_frame(actual, expected)
    assert_connected(actual)
    for key in ("section", "materials", "springs", "shape_eccentricity"):
        assert actual[key] == legacy[key]
    assert (geometry, legacy) == before
    assert build_frame_model(geometry, legacy, direction) == actual
    actual["materials"]["body"]["fck"] = -1
    actual["sections"]["body"]["area"] = -1
    assert (geometry, legacy) == before


@pytest.mark.parametrize("direction", ("b", "w"))
@pytest.mark.parametrize("h2,h3,hg,parapet", list(product((0, 1), (0, 0.5), (0, 1, 2), ("none", "center", "eccentric"))))
def test_all_boundary_endpoint_and_parapet_combinations(direction, h2, h3, hg, parapet):
    geometry, legacy, _ = case_inputs("default", direction)
    geometry.update(h1=0 if parapet == "none" else 0.5, h2=h2, h3=h3, h4=3, h5=0, h6=2,
                    b1=2, b2=0.5, b3=1, b4=0, b5=0,
                    w1=2, w2=0.5, w3=1, w4=0, w5=0)
    if parapet == "eccentric":
        geometry[f"{direction}2"] = 0.75
    legacy["nodes"][2]["y"] = hg
    frame = build_frame_model(geometry, legacy, direction)
    # Explicit aliases for each zero-height combination, independent of the
    # implementation's coordinate grouping and priority traversal.
    upper = {(0, 0): (1, 1), (0, 0.5): (1, 6), (1, 0): (5, 5), (1, 0.5): (5, 6)}[h2, h3]
    centroid = {0: 4, 1: 3, 2: 2}[hg]
    expected_ids = {"cap_top": 1, "footing_top": 2, "footing_centroid": centroid,
                    "footing_bottom": 4, "h2_h3": upper[0], "h3_h4": upper[1]}
    expected_members = []
    if h2:
        expected_members.append((1, 1, 5))
    if h3:
        expected_members.append((2, upper[0], 6))
    expected_members.append((3, upper[1], 2))
    if hg != 2:
        expected_members.append((4, 2, centroid))
    if hg != 0:
        expected_members.append((5, centroid, 4))
    if parapet != "none":
        base = 1 if parapet == "center" else 7
        expected_ids.update(parapet_base=base, parapet_top=8)
        if parapet == "eccentric":
            expected_members.append((6, 1, 7))
        expected_members.append((7, base, 8))
    assert frame["node_ids"] == expected_ids
    assert [(member["id"], member["node_i"], member["node_j"]) for member in frame["members"]] == expected_members
    assert frame["support_node_id"] == 4
    assert frame["load_anchors"] == {
        "cap_top": {"node_id": 1}, "footing_centroid": {"node_id": centroid},
        "column_line_load": {"from_node_id": 1, "to_node_id": 2,
                             "member_ids": ([1] if h2 else []) + ([2] if h3 else []) + [3]},
        "pedestal": {"equivalent_node_id": 1, "automatic_self_weight": False}}
    by_id = {node["id"]: node for node in frame["nodes"]}
    for role, identifier in expected_ids.items():
        assert role in by_id[identifier]["roles"]
    for node in frame["legacy_nodes"]:
        assert node["active_node_id"] == expected_ids[{1: "cap_top", 2: "footing_top", 3: "footing_centroid", 4: "footing_bottom"}[node["id"]]]
        assert node["source_row"] in by_id[node["active_node_id"]]["source_rows"]
    assert_connected(frame)


@pytest.mark.parametrize("direction", ("b", "w"))
@pytest.mark.parametrize("footing_height,expected_cap", ((0, 4), (2, 2)))
def test_complete_priority_when_all_upper_roles_coincide(direction, footing_height, expected_cap):
    geometry, legacy, _ = case_inputs("parapet_centered", direction)
    geometry.update(h2=0, h3=0, h4=0, h5=0, h6=footing_height)
    legacy["nodes"][2]["y"] = footing_height
    frame = build_frame_model(geometry, legacy, direction)
    for role in ("cap_top", "footing_top", "footing_centroid", "h2_h3", "h3_h4", "parapet_base"):
        assert frame["node_ids"][role] == expected_cap
    node = next(node for node in frame["nodes"] if node["id"] == expected_cap)
    first_row = 81 if direction == "b" else 79
    assert node["source_rows"] == list(range(first_row, first_row + (4 if footing_height == 0 else 3)))
    assert frame["support_node_id"] == 4
    assert_connected(frame)


@pytest.mark.parametrize("direction", ("b", "w"))
def test_centered_decimal_relation_and_real_tiny_signed_offsets(direction):
    geometry, legacy, _ = case_inputs("parapet_centered", direction)
    geometry.update({f"{direction}1": 0.6, f"{direction}2": 0,
                     f"{direction}3": 0.6, f"{direction}4": 0.3, f"{direction}5": 0.3})
    assert parapet_center(geometry, direction) == 0
    frame = build_frame_model(geometry, legacy, direction)
    assert frame["node_ids"]["parapet_base"] == frame["node_ids"]["cap_top"]
    geometry[f"{direction}2"] = 1e-100
    assert parapet_center(geometry, direction) == 1e-100
    frame = build_frame_model(geometry, legacy, direction)
    assert frame["node_ids"]["parapet_base"] == 7
    assert next(node for node in frame["nodes"] if node["id"] == 7)["x"] == 1e-100
    geometry[f"{direction}2"] = -1e-100
    assert parapet_center(geometry, direction) == -1e-100


@pytest.mark.parametrize("direction", ("b", "w"))
def test_mirrored_parapets_retain_horizontal_arm_and_vertical_h1(direction):
    geometry, legacy, _ = case_inputs("parapet_asymmetric", direction)
    negative = build_frame_model(geometry, legacy, direction)
    # Mirror about the body axis using the independently known sample offsets.
    geometry[f"{direction}2"] = 1.25 if direction == "b" else 7.05
    positive = build_frame_model(geometry, legacy, direction)
    minus = {node["id"]: node for node in negative["nodes"]}
    plus = {node["id"]: node for node in positive["nodes"]}
    assert plus[7]["x"] == -minus[7]["x"]
    assert plus[8]["x"] == plus[7]["x"]
    assert plus[1]["y"] == plus[7]["y"]
    assert positive["members"] == negative["members"]


@pytest.mark.parametrize("name", EXPECTATIONS)
@pytest.mark.parametrize("direction", ("b", "w"))
def test_split_uniform_column_load_preserves_force_and_base_first_moment(name, direction):
    geometry, legacy, _ = case_inputs(name, direction)
    frame = build_frame_model(geometry, legacy, direction)
    nodes = {node["id"]: node for node in frame["nodes"]}
    pieces = [member for member in frame["members"] if member["id"] in (1, 2, 3)]
    intensity = 17.25  # independent arbitrary uniform line load
    length = sum(geometry[key] for key in ("h2", "h3", "h4"))
    lower = geometry["h5"] + geometry["h6"]
    force = sum(intensity * (nodes[m["node_i"]]["y"] - nodes[m["node_j"]]["y"]) for m in pieces)
    moment = sum(intensity * (nodes[m["node_i"]]["y"] ** 2 - nodes[m["node_j"]]["y"] ** 2) / 2 for m in pieces)
    assert force == pytest.approx(intensity * length, rel=1e-14)
    assert moment == pytest.approx(intensity * length * (lower + length / 2), rel=1e-14)
    assert frame["load_anchors"]["column_line_load"]["member_ids"] == [member["id"] for member in pieces]
    assert frame["load_anchors"]["pedestal"]["automatic_self_weight"] is False


@pytest.mark.parametrize("direction", ("b", "w"))
@pytest.mark.parametrize("change,path", [
    ({"b3": 0}, "b3"), ({"w3": 0}, "w3"),
    ({"b3": 0.001, "w3": 0.001}, "b3/w3"),
    ({"b3": 0.01, "w3": 0.1}, "b3/w3"),
    ({"b3": float("inf")}, "b3"), ({"w3": float("nan")}, "w3"),
    ({"b3": 1e150, "w3": 1e150}, "b3/w3"),
    ({"h1": 1e-100}, "h1"), ({"h2": 1e-100}, "h2"),
    ({"h3": 1e-100}, "h3"), ({"h4": 1e-100}, "h4"),
    ({"h5": 1e-100}, "h5"), ({"h6": float("inf")}, "h6"),
    ({"h4": 1e308, "h3": 1e308}, "h3"),
])
def test_invalid_h1_sections_and_unrepresentable_heights_report_input_path(direction, change, path):
    geometry, legacy, _ = case_inputs("parapet_asymmetric", direction)
    geometry.update(change)
    with pytest.raises(InputError, match=f"{'0610' if direction == 'b' else '0620'}.*{path}"):
        build_frame_model(geometry, legacy, direction)


@pytest.mark.parametrize("direction", ("b", "w"))
def test_representable_tiny_positive_height_does_not_merge(direction):
    geometry, legacy, _ = case_inputs("default", direction)
    geometry["h2"] = 1e-13
    frame = build_frame_model(geometry, legacy, direction)
    assert frame["node_ids"]["cap_top"] != frame["node_ids"]["h2_h3"]
    assert frame["members"][0]["id"] == 1
    assert_connected(frame)


@pytest.mark.parametrize("direction", ("b", "w"))
def test_h6_positive_height_lost_beneath_h5_is_rejected(direction):
    geometry, legacy, _ = case_inputs("default", direction)
    geometry.update(h1=0, h2=1, h3=1, h4=1, h5=1, h6=1e-100)
    legacy["nodes"][2]["y"] = 0.5
    stage = "0610" if direction == "b" else "0620"
    with pytest.raises(InputError, match=f"{stage}.*input.geometry.h6.*座標精度"):
        build_frame_model(geometry, legacy, direction)


def test_builder_uses_legacy_ids_and_preserves_audit_rows_independent_of_array_order():
    geometry, legacy, expected = case_inputs("default", "b")
    legacy["nodes"].reverse()
    frame = build_frame_model(geometry, legacy, "b")
    assert_expected_frame(frame, expected)


def test_parapet_absent_requires_no_h1_section_or_center_geometry():
    geometry, legacy, _ = case_inputs("default", "b")
    for prefix in ("b", "w"):
        for index in range(1, 6):
            del geometry[f"{prefix}{index}"]
    frame = build_frame_model(geometry, legacy, "b")
    assert set(frame["sections"]) == {"body"}
    assert "parapet_top" not in frame["node_ids"]


def test_model_rejects_nonfinite_handoff_and_missing_material_reference():
    geometry, legacy, _ = case_inputs("default", "b")
    legacy["nodes"][2]["y"] = float("nan")
    with pytest.raises(InputError, match="0610.*nodes"):
        build_frame_model(geometry, legacy, "b")
    geometry, legacy, _ = case_inputs("default", "b")
    legacy["materials"] = {}
    with pytest.raises(InputError, match="0610.*参照"):
        build_frame_model(geometry, legacy, "b")


@pytest.mark.parametrize("path", [("section", "width"), ("materials", "body", "Ec"),
                                 ("springs", "long_term", "Kv")])
def test_retained_compatibility_values_must_remain_finite(path):
    geometry, legacy, _ = case_inputs("default", "b")
    target = legacy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = float("inf")
    with pytest.raises(InputError, match="0610.frame"):
        build_frame_model(geometry, legacy, "b")


def test_center_rejects_real_offset_below_coordinate_range_and_invalid_direction():
    geometry, _, _ = case_inputs("parapet_centered", "b")
    geometry.update(b1=0.6, b2=0, b3=0.6, b4=4e-323, b5=4.4e-323)
    with pytest.raises(InputError, match="0610.*geometry.*数値範囲"):
        parapet_center(geometry, "b")
    with pytest.raises(InputError, match="direction"):
        parapet_center(geometry, "x")
