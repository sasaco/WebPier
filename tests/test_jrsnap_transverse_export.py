"""Direction-specific physical oracles and longitudinal byte compatibility."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_jrsnap_export import calculation as longitudinal_calculation
from test_jrsnap_export import example_input, resultants

from src.calculator import calculate as calculate_foundation
from src.inputs import InputError, parse_input
from src.jrsnap_design_conditions import get_profile
from src.jrsnap_export import (
    build_longitudinal_ndu_model,
    build_transverse_ndu_model,
)
from src.jrsnap_ndu import serialize_ndu, validate_ndu_bytes
from src.longitudinal_design_conditions import (
    parse_longitudinal_design_conditions,
)
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.seismic_transverse_calculator import calculate_seismic_transverse
from src.transverse_calculator import calculate_transverse


def transverse_input():
    raw = example_input()
    raw["jrsnap_transverse"] = {"shear_factor_vcd": 2, "shear_factor_vsd": 1.3,
                                "shear_factor_vdd": 1.8, "aggregate_max_mm": 25}
    return raw


def calculation(raw=None):
    raw = transverse_input() if raw is None else raw
    sha = hashlib.sha256(json.dumps(raw, ensure_ascii=False).encode()).hexdigest()
    foundation = calculate_foundation(parse_input(raw))
    inputs = parse_reaction_input(raw)
    reactions = calculate_reactions(inputs)
    for result in (foundation, reactions):
        result["provenance"]["input_sha256"] = sha
    transverse = calculate_transverse(inputs, foundation, reactions,
                                      design_conditions=parse_longitudinal_design_conditions(raw))
    transverse["provenance"]["input_sha256"] = sha
    seismic = calculate_seismic_transverse(inputs, reactions, transverse)
    return raw, foundation, seismic, sha


def build(source):
    return build_transverse_ndu_model(*source)


def test_transverse_geometry_control_section_and_foundation_are_current_and_detached():
    source = calculation()
    before = deepcopy(source)
    model = build(source)
    assert source == before
    assert [node["y"] for node in model["nodes"]] == pytest.approx(
        [-10.35, -7.6, -5.6, -4.9, -.01, 0, 1.349999976158142, 2.7])
    assert model["metadata"]["roles"]["superstructure_b"] == model["metadata"]["roles"]["superstructure_c"] == 1
    assert model["metadata"]["roles"]["cap_top"] == 2
    assert model["metadata"]["settings"]["analysis"]["control_role"] == "superstructure_b"
    assert model["nonlinear"]["element"] == 5
    assert (model["section"]["width_mm"], model["section"]["height_mm"],
            model["section"]["shear_span_mm"]) == pytest.approx((2700, 4500, 10350))
    assert model["section"]["main_face_pitch_mm"] == 250
    assert model["section"]["main_face_layers"] == 1
    rows = model["section"]["rebar"]
    assert len(rows) == 31 and sum(row["count"] for row in rows) == 76
    assert rows[0] == {"center_mm": 102, "diameter_mm": 19, "count": 9, "material": "SD390"}
    assert rows[-1] == {"center_mm": 4398, "diameter_mm": 19, "count": 9, "material": "SD390"}
    assert model["section"]["hoop"] == {"fyk":390, "diameter_mm":22, "legs":6, "pitch_mm":150}
    assert (model["footing"]["B"], model["footing"]["L"], model["footing"]["kv"],
            model["footing"]["Df"], model["footing"]["gamma2"]) == (9, 7, 405976, 4.7, 12.3)
    assert [row["stiffness"] for row in model["supports"]] == [8525475, 25576488]


def test_nine_cases_preserve_signed_train_eccentricity_and_rightward_resultants():
    model = build(calculation())
    assert [case["increment"] for case in model["cases"]] == [0, 0, 0, 0, 0, 0, 1, 4, 1]
    assert model["combination"]["coefficients"] == [1, 1, 1, 1, 1, 0, 1, 1, 1]
    assert resultants(model, model["cases"][0]) == pytest.approx((0, 14729.3381953125, 0))
    assert resultants(model, model["cases"][4]) == pytest.approx((0, 480, -1028.62))
    assert resultants(model, model["cases"][5]) == pytest.approx((0, 480, 1028.62))
    assert resultants(model, model["cases"][6]) == pytest.approx((9090, 0, 120732))
    assert resultants(model, model["cases"][7]) == pytest.approx((144, 0, 2253.6))
    assert resultants(model, model["cases"][8]) == pytest.approx((4067.5425, 0, 22575.10315969409))
    for case in (model["cases"][0], model["cases"][8]):
        assert [load["element"] for load in case["member_loads"]] == [2, 3, 4, 5]
    assert [load["q_i"] for load in model["cases"][8]["member_loads"]] == [-595.35, -595.35, -297.68, -297.68]
    assert model["cases"][1]["joint_loads"][1]["node"] == 7  # soil remains at the footing centroid


def test_native_controls_fixed_combination_slots_and_longitudinal_bytes():
    native = serialize_ndu(build(calculation()))
    parsed = validate_ndu_bytes(native)
    records = parsed["records"]
    assert records["DataName"] == ["線路直角方向"]
    assert records["DataInfo"][2:6] == ["350", "1", "1000", "300"]
    assert records["DataInfo"][18] == "0.35"
    assert len(records["SNAPConb1"]) == 21
    assert list(map(float, records["SNAPConb1"][4:13])) == [1, 1, 1, 1, 1, 0, 1, 1, 1]
    assert records["SNAPConb1"][13:19] == [" "] * 6
    assert parsed["counts"]["joint_loads"] == 11
    # This fixed byte oracle is the already accepted WebPier longitudinal output.
    raw, foundation, seismic, sha = longitudinal_calculation(transverse_input())
    old_direction = serialize_ndu(build_longitudinal_ndu_model(raw, foundation, seismic, sha))
    assert hashlib.sha256(old_direction).hexdigest() == "02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71"


def test_equal_upper_height_change_updates_control_span_without_moving_actions():
    raw = transverse_input()
    for side in ("起点側", "終点側"):
        raw["上部構造"][side]["高さ"]["h2"] += .5
    model = build(calculation(raw))
    assert model["section"]["shear_span_mm"] == pytest.approx(10850)
    assert model["cases"][6]["joint_loads"][0]["node"] == model["metadata"]["roles"]["cap_top"]
    assert model["cases"][6]["joint_loads"][0]["M"] == 27105


def test_low_shear_span_still_rejects_bending_profile():
    raw = transverse_input()
    for side in ("起点側", "終点側"):
        raw["上部構造"][side]["高さ"].update(h1=0, h2=0)
    with pytest.raises(InputError, match="La/d<2"):
        build(calculation(raw))


def test_asymmetric_footing_and_directional_hoops_are_not_longitudinal_aliases():
    raw = transverse_input()
    raw["下部構造"]["寸法"]["正面"]["W9"] += .4
    hoop = next(row for row in raw["鉄筋"]["柱"]["column_hoops"]["direction_rows"] if row["direction"] == "直角")
    hoop.update(effective_legs=8, pitch_mm=175)
    source = calculation(raw)
    model = build(source)
    assert model["footing"]["B"] == source[1]["foundation"]["L"]
    assert model["footing"]["L"] == source[1]["foundation"]["B"]
    assert model["section"]["hoop"]["legs"] == 8
    assert model["section"]["hoop"]["pitch_mm"] == 175


def test_h1_has_one_equivalent_point_and_no_upper_distributed_load():
    raw = transverse_input()
    raw["下部構造"]["寸法"]["高さ"]["H1"] = 1.2
    raw["下部構造"]["寸法"]["側面"]["B3"] = .8
    raw["下部構造"]["寸法"]["正面"]["W3"] = 1.6
    source = calculation(raw)
    model = build(source)
    point = model["cases"][8]["joint_loads"][0]
    assert point["node"] == model["metadata"]["roles"]["cap_top"]
    assert (point["H"], point["M"]) == (source[2]["inertia"]["pedestal"]["H"], source[2]["inertia"]["pedestal"]["M"])
    ids = {load["element"] for load in model["cases"][8]["member_loads"]}
    assert not any(member["id"] in ids for member in model["members"] if member["region"] in ("h1", "upper_geometry"))


@pytest.mark.parametrize("mutate,match", [
    (lambda raw: raw.pop("jrsnap_transverse"), "jrsnap_transverse"),
    (lambda raw: raw["上部構造"]["起点側"]["高さ"].update(h2=3), "B/C上部構造"),
    (lambda raw: raw["鉄筋"]["柱"]["main_rows"][1].update(center_mm=225), "先頭・末尾.*直角主筋"),
])
def test_ambiguous_directional_inputs_rejected(mutate, match):
    raw = transverse_input()
    mutate(raw)
    with pytest.raises(InputError, match=match):
        build(calculation(raw))


@pytest.mark.parametrize("key", ["shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "aggregate_max_mm"])
@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), 0, -1])
def test_transverse_settings_are_explicit_and_finite(key, value):
    raw = transverse_input()
    raw["jrsnap_transverse"][key] = value
    with pytest.raises(InputError, match="jrsnap_transverse"):
        get_profile(raw, "transverse")


@pytest.mark.parametrize("mutation,match", [
    (lambda s: s["frame"]["node_ids"].update(superstructure_b=2), "役割superstructure_b"),
    (lambda s: s["combinations"][0]["coefficients"].__setitem__(5, 1), "組合せ"),
    (lambda s: s["basic_cases"][7].update(load_type="incremental"), "基本ケース8"),
    (lambda s: s["actions"]["train_down"]["points"][0].update(M=0), "loadsがactions"),
    (lambda s: s["input"]["spans"]["b"].update(hs=0), "上部工・荷重入力世代"),
])
def test_transverse_snapshot_semantics_rejected(mutation, match):
    source = calculation()
    mutation(source[2])
    with pytest.raises(InputError, match=match):
        build(source)


def test_builder_does_not_read_saved_files(monkeypatch):
    source = calculation()
    def forbidden(*args, **kwargs):
        raise AssertionError("NDU builder attempted saved-file access")
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert len(build(source)["cases"]) == 9


@pytest.mark.parametrize("record,index,value", [
    ("DataInfo", 2, "300"),
    ("DataInfo", 5, "200"),
    ("DataInfo", 18, "-0.35"),
    ("SNAPConb1", 9, "1"),
    ("SNAPConb1", 13, "1"),
    ("ConbAlpf1", 5, "1"),
    ("JLoadInfo10", 3, "1"),  # Case 8 EQL must remain limited incremental (4).
    ("FootInfo1", 7, "NaN"),
])
def test_native_transverse_profile_and_case_corruption_rejected(record, index, value):
    lines = serialize_ndu(build(calculation())).decode("cp932").splitlines()
    for position, line in enumerate(lines):
        if line.startswith(record + "="):
            fields = line.split("=", 1)[1].split(",")
            fields[index] = value
            lines[position] = record + "=" + ",".join(fields)
            break
    else:
        raise AssertionError("test target record missing")
    with pytest.raises(InputError):
        validate_ndu_bytes(("\r\n".join(lines) + "\r\n").encode("cp932"))
