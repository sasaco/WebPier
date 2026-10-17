"""0710 independent reference values and input-sensitive action contracts."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import struct

import pytest

from src.calculator import calculate as calculate_foundation
from src.inputs import InputError, parse_input
from src.longitudinal_calculator import calculate_longitudinal
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.seismic_longitudinal_calculator import calculate_seismic_longitudinal


FIXTURES = Path(__file__).parent / "fixtures"
REFERENCE = json.loads((FIXTURES / "seismic_longitudinal_example2.json").read_text(encoding="utf-8"))
CURRENT = json.loads((FIXTURES / "seismic_longitudinal_current_input.json").read_text(encoding="utf-8"))


def rounded(value, places=2):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def single(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def assert_top_down_references(frame):
    nodes = frame["nodes"]
    assert [node["id"] for node in nodes] == list(range(1, len(nodes) + 1))
    assert [(node["y"], node["x"]) for node in nodes] == sorted(
        ((node["y"], node["x"]) for node in nodes), key=lambda position: (-position[0], position[1]))
    by_id = {node["id"]: node for node in nodes}
    for role, identifier in frame["node_ids"].items():
        assert role in by_id[identifier]["roles"]
    members = frame["members"]
    assert [member["id"] for member in members] == list(range(1, len(members) + 1))
    midpoints = []
    for member in members:
        first, second = by_id[member["node_i"]], by_id[member["node_j"]]
        midpoints.append(((first["y"] + second["y"]) / 2, (first["x"] + second["x"]) / 2))
    assert midpoints == sorted(midpoints, key=lambda position: (-position[0], position[1]))
    metadata = frame["column_base_micro_member"]
    micro = next(member for member in members if member["id"] == metadata["member_id"])
    assert micro["region"] == "column_base_micro_member"
    assert micro["node_i"] == metadata["node_id"] == frame["node_ids"]["column_base_micro_top"]
    assert micro["node_j"] == frame["node_ids"]["footing_top"]


def assert_original_geometry_preserved(original, frame):
    original_nodes = {node["id"]: node for node in original["nodes"]}
    nodes = {node["id"]: node for node in frame["nodes"]}
    for source in original["nodes"]:
        actual = nodes[frame["node_ids"][source["roles"][0]]]
        assert {key: actual[key] for key in ("x", "y", "roles")} == {
            key: source[key] for key in ("x", "y", "roles")}
    members = {member["region"]: member for member in frame["members"]}
    for source in original["members"]:
        actual = members[source["region"]]
        for key in ("region", "behavior", "section_ref", "material_ref"):
            assert actual[key] == source[key]
        for end in ("node_i", "node_j"):
            if source["region"] == "h4" and end == "node_j":
                assert actual[end] == frame["node_ids"]["column_base_micro_top"]
            else:
                assert [(nodes[actual[end]])[axis] for axis in ("x", "y")] == [
                    original_nodes[source[end]][axis] for axis in ("x", "y")]


def upstream(source, inputs=None):
    inputs = inputs or source["inputs"]
    return calculate_longitudinal(inputs, source["foundation"], calculate_reactions(inputs),
                                  design_conditions=source["conditions"])


@pytest.fixture(scope="module")
def source():
    raw = (FIXTURES / "seismic_longitudinal_input.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CURRENT["input_sha256"]
    data = json.loads(raw)
    result = {"inputs": parse_reaction_input(data), "foundation": calculate_foundation(parse_input(data)),
              "conditions": parse_longitudinal_design_conditions(data)}
    result["longitudinal"] = upstream(result)
    result["longitudinal"]["provenance"]["input_sha256"] = CURRENT["input_sha256"]
    return result


@pytest.fixture
def canonical(source):
    return deepcopy(source["longitudinal"])


def test_independent_reference_all_printed_actions_and_case_semantics(canonical):
    result = calculate_seismic_longitudinal(canonical)
    assert (result["schema_version"], result["stage"], result["direction"]) == (1, "0710", "longitudinal")
    assert result["case_model_version"] == "seismic-longitudinal-example2-v1"
    assert result["vertical"]["train"]["earthquake"] == REFERENCE["train"]
    for action in ("girder", "train"):
        for side in ("B", "C"):
            assert result["horizontal"][action][side] == REFERENCE["horizontal"][action][side]
    for component, value in REFERENCE["inertia"].items():
        assert result["inertia"][component] == value
    assert result["vertical"]["water"]["normal"]["N"] == REFERENCE["normal_water"]["N"]
    assert {key: result["vertical"]["snow"]["s2"][key] for key in ("N", "M")} == REFERENCE["snow_s2"]
    assert [{key: row[key] for key in expected} for row, expected in
            zip(result["basic_cases"], REFERENCE["basic_cases"], strict=True)] == REFERENCE["basic_cases"]
    assert result["combinations"] == REFERENCE["combinations"]
    assert result["provenance"]["input_sha256"] == CURRENT["input_sha256"]


def test_current_input_zero_components_are_distinct_from_pdf_transcription(canonical):
    result = calculate_seismic_longitudinal(canonical)
    for component, value in CURRENT["inertia"].items():
        assert result["inertia"][component] == value
    for component, value in CURRENT["unrounded"].items():
        assert result["formulas"][component]["unrounded"] == pytest.approx(value)
        assert result["formulas"][component]["value"] == result["inertia"][component]
    assert "pedestal" not in REFERENCE["inertia"]
    assert "beam_bottom" not in REFERENCE["inertia"]
    assert result["formulas"]["beam_bottom"] is not result["formulas"]["column"]
    assert [row["id"] for row in result["frame"]["nodes"]] == CURRENT["frame_node_ids"]
    assert [row["id"] for row in result["frame"]["members"]] == CURRENT["frame_member_ids"]


def test_signed_actions_and_already_applied_coefficients_are_not_applied_twice(canonical):
    result = calculate_seismic_longitudinal(canonical)
    water = result["basic_cases"][2]
    assert water["direction"] == "up"
    assert water["loads"]["N"] == -1701.0
    assert result["basic_cases"][5]["loads"]["B"] == 6790.0
    assert result["basic_cases"][6]["loads"]["B"] == 64.0
    assert result["horizontal"]["train"]["Kh"] == .2
    assert result["horizontal"]["train"]["coefficient_applied"] is True
    assert result["basic_cases"][6]["coefficient"] == 1.0
    assert result["basic_cases"][6]["load_type"] == "limited_incremental"
    assert result["inertia"]["Kh"] == 1.0


def test_result_is_detached_and_excludes_support_models_and_old_combinations(canonical):
    before = deepcopy(canonical)
    canonical["legacy_audit"]["combinations"] = [{"sentinel": "DO_NOT_PUBLISH"}]
    result = calculate_seismic_longitudinal(canonical)
    before["legacy_audit"]["combinations"] = [{"sentinel": "DO_NOT_PUBLISH"}]
    assert canonical == before
    assert result["input"] == canonical["input"]
    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in ("springs", "spring_provenance", '"Kv"', '"Ks"', '"Kr"', "support_node_id",
                      "fixed_base", "restraints", "constitutive_law", "nonlinear_springs",
                      "DO_NOT_PUBLISH", '"legacy_nodes"', '"cells"'):
        assert forbidden not in serialized
    assert "legacy_audit" not in result
    result["input"]["geometry"]["b1"] = 999
    result["frame"]["nodes"][0]["roles"].append("mutated")
    result["basic_cases"][0]["loads"]["top"]["N"] = 999
    assert canonical == before
    assert result["vertical"]["fixed"]["top"]["N"] != 999


@pytest.mark.parametrize("load,b,c,total,moment,hb,hc", [
    (40.0, 400.0, 200.0, 600.0, 5.0, 80.0, 80.0),
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
])
def test_earthquake_line_load_controls_vertical_and_train_horizontal(source, load, b, c, total, moment, hb, hc):
    inputs = replace(source["inputs"], train=replace(source["inputs"].train, earthquake_load=load))
    result = calculate_seismic_longitudinal(upstream(source, inputs))
    train = result["vertical"]["train"]["earthquake"]
    assert (train["B"]["N"], train["C"]["N"], train["N"], train["M"]) == (b, c, total, moment)
    assert (result["horizontal"]["train"]["B"], result["horizontal"]["train"]["C"]) == (hb, hc)
    assert result["horizontal"]["girder"]["B"] == 6790.0


def test_whole_girder_lengths_drive_both_earthquake_reactions(source):
    inputs = source["inputs"]
    inputs = replace(inputs, spans=replace(inputs.spans,
                     b=replace(inputs.spans.b, span=22.85), c=replace(inputs.spans.c, span=11.25)))
    result = calculate_seismic_longitudinal(upstream(source, inputs))
    train = result["vertical"]["train"]["earthquake"]
    assert (train["B"]["N"], train["C"]["N"], train["N"]) == (384.0, 192.0, 576.0)
    assert train["M"] == -124.8 + 129.6  # No second rounding after the side moments are added.
    assert (result["horizontal"]["train"]["B"], result["horizontal"]["train"]["C"]) == (single(76.8), single(76.8))
    assert result["horizontal"]["girder"]["B"] == 6790.0


def test_swapped_bearings_keep_full_or_half_whole_girder_force(source):
    inputs = source["inputs"]
    inputs = replace(inputs, spans=replace(inputs.spans,
                     b=replace(inputs.spans.b, bearing="固定"), c=replace(inputs.spans.c, bearing="可動")))
    result = calculate_seismic_longitudinal(upstream(source, inputs))
    assert (result["horizontal"]["girder"]["B"], result["horizontal"]["girder"]["C"]) == (13580.0, 2370.0)
    assert (result["horizontal"]["train"]["B"], result["horizontal"]["train"]["C"]) == (128.0, 32.0)
    assert result["vertical"]["train"]["earthquake"] == REFERENCE["train"]


def test_signed_bearing_arms_change_moments_without_changing_force(source):
    inputs = source["inputs"]
    inputs = replace(inputs, spans=replace(inputs.spans,
                     b=replace(inputs.spans.b, f=.4), c=replace(inputs.spans.c, f=.8)))
    result = calculate_seismic_longitudinal(upstream(source, inputs))
    train = result["vertical"]["train"]["earthquake"]
    assert train == {"B": {"N": 320.0, "arm": -.4, "M": -128.0},
                     "C": {"N": 160.0, "arm": .8, "M": 128.0}, "N": 480.0, "M": 0.0}
    assert result["vertical"]["snow"]["s2"]["M"] == 16.0
    assert result["horizontal"]["train"]["total"] == 128.0


@pytest.mark.parametrize("change,expected", [("d2", 6840.0), ("s2", 6830.0)])
def test_remote_a_loads_participate_in_longitudinal_girder_inertia(source, change, expected):
    inputs = source["inputs"]
    if change == "d2":
        inputs = replace(inputs, dead=replace(inputs.dead, a=replace(inputs.dead.a, d2=760.0)))
    else:
        inputs = replace(inputs, snow=replace(inputs.snow, a=(540.0, *inputs.snow.a[1:])))
    result = calculate_seismic_longitudinal(upstream(source, inputs))
    assert result["horizontal"]["girder"]["B"] == expected
    assert result["horizontal"]["girder"]["C"] == 4740.0
    assert result["vertical"]["snow"]["s2"]["N"] == 710.0
    assert result["horizontal"]["train"]["total"] == 128.0


def test_nonseismic_snow_cases_do_not_change_earthquake_actions(source):
    inputs = source["inputs"]
    def changed(rows):
        return tuple((row[0], row[1] + 50, row[2] + 100) for row in rows)
    inputs = replace(inputs, snow=replace(inputs.snow, b=changed(inputs.snow.b), c=changed(inputs.snow.c),
                     a=(460, 1500, 1800), d=(250, 1200, 1400)))
    result = calculate_seismic_longitudinal(upstream(source, inputs))
    baseline = calculate_seismic_longitudinal(source["longitudinal"])
    for key in ("horizontal", "inertia", "vertical", "basic_cases"):
        assert result[key] == baseline[key]


def test_nonround_geometry_weights_and_nonzero_pedestal_follow_current_input(source):
    inputs = source["inputs"]
    geometry = replace(inputs.geometry, b1=3.113, w1=9.377, b4=.131, b5=.177, w4=1.671, w5=2.143,
                       b6=2.719, w6=4.637, h1=.837, b2=.253, b3=1.217, w2=1.003, w3=2.137,
                       h5=.457, unit_weight_body=25.237, unit_weight_footing=26.173,
                       unit_weight_displaced_soil=18.431)
    inputs = replace(inputs, geometry=geometry)
    canonical = upstream(source, inputs)
    result = calculate_seismic_longitudinal(canonical)
    assert result["inertia"]["beam_top"] == rounded(3.113 * 9.377 * 25.237)
    assert result["inertia"]["beam_bottom"] == rounded((3.113 - .131 - .177) * (9.377 - 1.671 - 2.143) * 25.237)
    assert result["inertia"]["column"] == rounded(2.719 * 4.637 * 25.237)
    assert len({result["inertia"][key] for key in ("beam_top", "beam_bottom", "column")}) == 3
    pedestal_h = single(rounded(rounded(1.217 * 2.137, 3) * .837 * 25.237))
    assert result["inertia"]["pedestal"]["H"] == pedestal_h
    assert result["inertia"]["pedestal"]["height"] == single(.837 / 2)
    assert result["inertia"]["pedestal"]["M"] == rounded(pedestal_h * single(.837 / 2))
    footing_weight = canonical["vertical"]["fixed"]["footing"]["N"]
    assert result["inertia"]["footing"] == rounded(footing_weight / 26.173 * (26.173 - 18.431))
    assert result["formulas"]["footing"]["factors"]["weight"] == footing_weight
    assert result["formulas"]["footing"]["geometry"]["h5"] == .457
    assert result["formulas"]["beam_top"]["factors"] == {"b": 3.113, "w": 9.377, "unit_weight": 25.237, "Kh": 1.0}
    assert_top_down_references(result["frame"])
    assert_original_geometry_preserved(canonical["frame"], result["frame"])
    new_id = result["frame"]["node_ids"]["column_base_micro_top"]
    assert result["frame"]["node_ids"]["parapet_top"] == 1
    assert len(result["frame"]["nodes"]) == len(canonical["frame"]["nodes"]) + 1
    new_node = next(node for node in result["frame"]["nodes"] if node["id"] == new_id)
    footing_top = next(node for node in canonical["frame"]["nodes"] if "footing_top" in node["roles"])
    assert new_node["y"] == pytest.approx(footing_top["y"] + .01)
    assert result["frame"]["members"][0]["region"] == "h1"
    assert result["input"]["geometry"]["b1"] == 3.113


@pytest.mark.parametrize("path", [
    ("vertical", "water", "normal", "N"), ("vertical", "snow", "s2", "M"),
    ("legacy_audit", "vertical", "train", "earthquake", "B", "arm"),
    ("legacy_audit", "inertia", "pedestal", "H"), ("input", "geometry", "b1"),
    ("frame", "nodes", 0, "x"), ("frame", "sections", "body", "area"),
])
@pytest.mark.parametrize("bad", [None, True, "1", float("inf"), float("nan")])
def test_selected_numeric_paths_reject_missing_types_and_nonfinite(canonical, path, bad):
    value = canonical
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = bad
    with pytest.raises(InputError, match="0710"):
        calculate_seismic_longitudinal(canonical)


@pytest.mark.parametrize("path", [
    ("vertical", "fixed", "column", "intensity"), ("vertical", "additional", "top", "B", "N"),
    ("legacy_audit", "vertical", "train", "earthquake", "C", "M"),
    ("legacy_audit", "inertia", "beam_bottom"), ("input", "geometry", "h5"),
])
def test_missing_selected_fields_fail_explicitly(canonical, path):
    value = canonical
    for key in path[:-1]:
        value = value[key]
    del value[path[-1]]
    with pytest.raises(InputError, match="0710"):
        calculate_seismic_longitudinal(canonical)


@pytest.mark.parametrize("key,value", [("schema_version", 1), ("schema_version", True),
                                       ("schema_version", 2.0), ("stage", "0620")])
def test_only_canonical_0610_schema_is_accepted(canonical, key, value):
    canonical[key] = value
    with pytest.raises(InputError, match="schema_version=2"):
        calculate_seismic_longitudinal(canonical)


@pytest.mark.parametrize("identifier", [9, 10])
@pytest.mark.parametrize("problem", ["missing", "duplicate", "label", "number_type", "force_bool"])
def test_horizontal_cases_are_unique_and_have_expected_semantics(canonical, identifier, problem):
    rows = canonical["legacy_audit"]["horizontal"]
    row = next(row for row in rows if row["case"] == identifier)
    if problem == "missing":
        rows.remove(row)
    elif problem == "duplicate":
        rows.append(deepcopy(row))
    elif problem == "label":
        row["label"] = "列車荷重慣性力 Kh=0.30"
    elif problem == "number_type":
        row["case"] = float(identifier)
    else:
        row["B"] = True
    with pytest.raises(InputError, match="0710"):
        calculate_seismic_longitudinal(canonical)


def test_unit_pier_coefficient_and_consistent_formula_values_required(canonical):
    canonical["legacy_audit"]["inertia"]["Kh"] = .2
    with pytest.raises(InputError, match="Kh=1.00"):
        calculate_seismic_longitudinal(canonical)
    canonical["legacy_audit"]["inertia"]["Kh"] = 1.0
    canonical["legacy_audit"]["inertia"]["beam_bottom"] += 1
    with pytest.raises(InputError, match="beam_bottom"):
        calculate_seismic_longitudinal(canonical)


@pytest.mark.parametrize("bad", [[], {}, True, "missing"])
def test_malformed_elastic_member_references_raise_inputerror(canonical, bad):
    canonical["frame"]["members"][0]["section_ref"] = bad
    with pytest.raises(InputError, match="断面・材料"):
        calculate_seismic_longitudinal(canonical)


def test_provenance_sha_is_preserved_or_optional_but_not_malformed(canonical):
    canonical["provenance"]["input_sha256"] = "bad"
    with pytest.raises(InputError, match="input_sha256"):
        calculate_seismic_longitudinal(canonical)
    del canonical["provenance"]["input_sha256"]
    assert "input_sha256" not in calculate_seismic_longitudinal(canonical)["provenance"]


@pytest.mark.parametrize("change", ["pedestal_product", "footing_dimension_sum"])
def test_derived_formula_overflow_is_an_explicit_inputerror(canonical, change):
    if change == "pedestal_product":
        canonical["legacy_audit"]["inertia"]["pedestal"].update(H=1e308, height=1e308)
    else:
        canonical["input"]["geometry"].update(b7=1e308, b8=1e308, b9=1e308)
    with pytest.raises(InputError, match="0710"):
        calculate_seismic_longitudinal(canonical)


def test_column_base_micro_member_splits_h4_without_moving_existing_geometry(canonical):
    before = deepcopy(canonical)
    result = calculate_seismic_longitudinal(canonical)
    frame, expected = result["frame"], CURRENT["column_base_micro_member"]
    assert frame["frame_spec_version"] == "seismic-longitudinal-column-base-micro-v2"
    assert frame["column_base_micro_member"] == {
        key: expected[key] for key in ("node_id", "member_id", "nominal_length")}
    assert frame["node_ids"]["footing_top"] == 5
    assert frame["node_ids"]["column_base_micro_top"] == expected["node_id"]
    nodes = {node["id"]: node for node in frame["nodes"]}
    assert nodes[expected["node_id"]] == {
        "id": expected["node_id"], "x": expected["node_x"], "y": expected["node_y"],
        "roles": ["column_base_micro_top"],
    }
    assert max(node["y"] for node in frame["nodes"]) == expected["total_height"]
    assert_top_down_references(frame)
    assert_original_geometry_preserved(canonical["frame"], frame)
    column = next(member for member in frame["members"] if member["region"] == "h4")
    assert (column["id"], column["node_i"], column["node_j"]) == (3, 3, 4)
    assert nodes[column["node_i"]]["y"] - nodes[column["node_j"]]["y"] == pytest.approx(expected["remaining_h4_length"])
    micro = next(member for member in frame["members"] if member["id"] == expected["member_id"])
    assert micro == {"id": expected["member_id"], "node_i": expected["node_id"], "node_j": 5,
                     **{key: expected[key] for key in ("region", "behavior", "section_ref", "material_ref")}}
    assert nodes[micro["node_i"]]["y"] - nodes[micro["node_j"]]["y"] == pytest.approx(.01)
    assert [(member["node_i"], member["node_j"]) for member in frame["members"]] == [
        (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
    assert [member["id"] for member in frame["members"] if member["behavior"] == "nonlinear"] == [expected["member_id"]]
    assert result["input"] == canonical["input"]
    assert canonical == before
    assert {tuple(row["physical_pages"]) for row in result["provenance"]["references"]
            if row["purpose"] == "column_base_micro_member"} == {(1, 2, 3, 4, 5)}
    assert "構成則・解析は未定義" in result["provenance"]["model_scope"]


@pytest.mark.parametrize("with_h1", [False, True])
def test_top_down_numbering_is_independent_of_input_array_order(source, with_h1):
    inputs = source["inputs"]
    if with_h1:
        inputs = replace(inputs, geometry=replace(inputs.geometry, h1=.5, b2=.5, b3=1, w2=1, w3=2))
    canonical = upstream(source, inputs)
    baseline = calculate_seismic_longitudinal(canonical)
    canonical["frame"]["nodes"].reverse()
    canonical["frame"]["members"].reverse()
    before = deepcopy(canonical)
    reordered = calculate_seismic_longitudinal(canonical)
    assert reordered == baseline
    assert_top_down_references(reordered["frame"])
    assert_original_geometry_preserved(canonical["frame"], reordered["frame"])
    assert canonical == before


@pytest.mark.parametrize("height", [0.0, .005, .01])
def test_h4_must_exceed_the_prescribed_micro_length(source, height):
    inputs = replace(source["inputs"], geometry=replace(source["inputs"].geometry, h4=height))
    canonical = upstream(source, inputs)
    with pytest.raises(InputError, match="H4.*0.010"):
        calculate_seismic_longitudinal(canonical)


@pytest.mark.parametrize("height", [.02, 7.3])
def test_changed_column_height_retains_a_complete_positive_member_chain(source, height):
    inputs = replace(source["inputs"], geometry=replace(source["inputs"].geometry, h4=height))
    canonical = upstream(source, inputs)
    frame = calculate_seismic_longitudinal(canonical)["frame"]
    nodes = {node["id"]: node for node in frame["nodes"]}
    edges = []
    for region in ("h4", "column_base_micro_member"):
        member = next(member for member in frame["members"] if member["region"] == region)
        length = nodes[member["node_i"]]["y"] - nodes[member["node_j"]]["y"]
        assert length > 0
        edges.append(length)
    assert edges[0] == pytest.approx(height - .01)
    assert edges[1] == pytest.approx(.01)
    assert sum(edges) == pytest.approx(height)
    assert max(node["y"] for node in frame["nodes"]) == max(node["y"] for node in canonical["frame"]["nodes"])


@pytest.mark.parametrize("base", [2.0 ** 45, 2.0 ** 53])
def test_micro_length_cannot_be_distorted_or_lost_at_large_coordinates(canonical, base):
    bottom_id = canonical["frame"]["node_ids"]["footing_top"]
    column = next(member for member in canonical["frame"]["members"] if member["region"] == "h4")
    for node in canonical["frame"]["nodes"]:
        if node["id"] == bottom_id:
            node["y"] = base
        elif node["id"] == column["node_i"]:
            node["y"] = base + 4
    with pytest.raises(InputError, match="座標精度"):
        calculate_seismic_longitudinal(canonical)


def test_positive_h4_remainder_cannot_disappear_at_coordinate_precision(source):
    height = math.nextafter(.01, math.inf)
    inputs = replace(source["inputs"], geometry=replace(source["inputs"].geometry, h4=height))
    canonical = upstream(source, inputs)
    with pytest.raises(InputError, match="座標精度"):
        calculate_seismic_longitudinal(canonical)


@pytest.mark.parametrize("problem", ["missing", "duplicate", "disconnected", "inclined"])
def test_invalid_h4_connection_is_rejected_instead_of_inserting_elsewhere(canonical, problem):
    members = canonical["frame"]["members"]
    column = next(member for member in members if member["region"] == "h4")
    if problem == "missing":
        members.remove(column)
    elif problem == "duplicate":
        members.append({**column, "id": max(member["id"] for member in members) + 1})
    elif problem == "disconnected":
        column["node_j"] = canonical["frame"]["node_ids"]["footing_bottom"]
    else:
        top = next(node for node in canonical["frame"]["nodes"] if node["id"] == column["node_i"])
        top["x"] += .5
    with pytest.raises(InputError, match="H4部材"):
        calculate_seismic_longitudinal(canonical)
