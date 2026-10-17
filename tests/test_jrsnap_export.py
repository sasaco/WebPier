"""Input-sensitive NDU conversion checks; expectations are physical quantities."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_column_rebar_reference import reference_column_input

from src import rebar_model
from src.calculator import calculate as calculate_foundation
from src.inputs import InputError, parse_input
from src.jrsnap_export import build_longitudinal_ndu_model
from src.longitudinal_calculator import calculate_longitudinal
from src.longitudinal_design_conditions import (
    parse_longitudinal_design_conditions,
)
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.seismic_longitudinal_calculator import calculate_seismic_longitudinal


def example_input():
    raw = json.loads((Path(__file__).parent / "fixtures/seismic_longitudinal_input.json").read_text(encoding="utf-8"))
    raw.setdefault("鉄筋", {}).update(version=2, 柱=reference_column_input())
    for name in ("梁", "フーチング"):
        raw["鉄筋"].setdefault(name, {"concrete_strength_mpa": 27})
    # Explicit test input, not a product default or amendment to project input.
    raw["jrsnap_longitudinal"] = {"shear_factor_vcd": 2, "shear_factor_vsd": 1.3,
                                  "shear_factor_vdd": 1.8, "aggregate_max_mm": 25}
    return raw


def calculation(raw=None):
    raw = example_input() if raw is None else raw
    sha = hashlib.sha256(json.dumps(raw, ensure_ascii=False).encode()).hexdigest()
    foundation = calculate_foundation(parse_input(raw))
    inputs = parse_reaction_input(raw)
    reactions = calculate_reactions(inputs)
    for result in (foundation, reactions):
        result["provenance"]["input_sha256"] = sha
    longitudinal = calculate_longitudinal(inputs, foundation, reactions,
                                         design_conditions=parse_longitudinal_design_conditions(raw))
    longitudinal["provenance"]["input_sha256"] = sha
    seismic = calculate_seismic_longitudinal(longitudinal)
    return raw, foundation, seismic, sha


def build(source):
    raw, foundation, seismic, sha = source
    return build_longitudinal_ndu_model(raw, foundation, seismic, input_sha256=sha)


def test_current_geometry_rebar_support_and_sources_are_detached():
    source = calculation()
    before = deepcopy(source)
    model = build(source)
    assert source == before
    assert [node["y"] for node in model["nodes"]] == pytest.approx([-7.6, -5.6, -4.9, -.01, 0, 1.349999976158142, 2.7])
    assert [(row["node_i"], row["node_j"], row["kind"]) for row in model["elements"]] == [
        (1, 2, 1), (2, 3, 1), (3, 4, 1), (4, 5, 2), (5, 6, 1), (6, 7, 1)]
    assert model["section"]["rebar"] == [
        {"center_mm": 108, "diameter_mm": 32, "count": 29, "material": "SD390"},
        *[{"center_mm": center, "diameter_mm": 19, "count": 2, "material": "SD390"}
          for center in range(350, 2351, 250)],
        {"center_mm": 2592, "diameter_mm": 32, "count": 29, "material": "SD390"}]
    assert [row["stiffness"] for row in model["supports"]] == [8525475, 25576488]
    assert (model["footing"]["Df"], model["footing"]["gamma2"], model["footing"]["gamma1"]) == (4.7, 12.3, 10)
    assert model["section"]["shear_span_mm"] == pytest.approx(7600)
    assert model["section"]["Ec"] == 26.5
    model["metadata"]["settings"]["analysis"]["steps"] = 1
    assert build(source)["metadata"]["settings"]["analysis"]["steps"] == 300


def resultants(model, case):
    nodes = {row["id"]: row for row in model["nodes"]}
    elements = {row["id"]: row for row in model["elements"]}
    bottom = nodes[model["metadata"]["roles"]["footing_bottom"]]
    h = n = m = 0.
    for row in case["joint_loads"]:
        node = nodes[row["node"]]
        h += row["H"]
        n += row["N"]
        m += row["M"] + (node["x"] - bottom["x"]) * row["N"] - (node["y"] - bottom["y"]) * row["H"]
    for row in case["member_loads"]:
        element = elements[row["element"]]
        first, second = nodes[element["node_i"]], nodes[element["node_j"]]
        length = second["y"] - first["y"]
        if row["kind"] == 4:
            n += row["q_i"] * length
            m += (first["x"] - bottom["x"]) * row["q_i"] * length
        else:
            # Integral of a linear load, independent of the exporter record code.
            force = length * (row["q_i"] + row["q_j"]) / 2
            first_moment = length**2 * (row["q_i"] + 2 * row["q_j"]) / 6
            h -= force
            m += (first["y"] - bottom["y"]) * force + first_moment
    return h, n, m


def test_eight_case_resultants_and_micro_distribution():
    model = build(calculation())
    assert [case["increment"] for case in model["cases"]] == [0, 0, 0, 0, 0, 1, 4, 1]
    assert [len(case["member_loads"]) for case in model["cases"]] == [4, 0, 0, 0, 0, 0, 0, 4]
    for case in (model["cases"][0], model["cases"][7]):
        assert [load["element"] for load in case["member_loads"]] == [1, 2, 3, 4]
    assert resultants(model, model["cases"][0]) == pytest.approx((0, 14729.3381953125, -610), abs=1e-8)
    assert resultants(model, model["cases"][6]) == pytest.approx((-128, 0, -1318.4))
    # hG is the upstream VBA Single 1.350000023841858, not display 1.35.
    assert resultants(model, model["cases"][7]) == pytest.approx((-4067.5425, 0, -22575.10315969409), abs=1e-8)


def test_h1_offset_shape_keeps_geometry_and_equivalent_pedestal_action():
    raw = example_input()
    raw["下部構造"]["寸法"]["高さ"]["H1"] = 1.2
    raw["下部構造"]["寸法"]["側面"]["B3"] = .8
    raw["下部構造"]["寸法"]["正面"]["W3"] = 1.6
    source = calculation(raw)
    model = build(source)
    source_points = {(node["x"], node["y"]) for node in source[2]["frame"]["nodes"]}
    origin = next(node["y"] for node in source[2]["frame"]["nodes"] if "footing_top" in node["roles"])
    assert {(node["x"], origin - node["y"]) for node in model["nodes"]} == source_points
    pedestal = model["cases"][7]["joint_loads"][-1]
    assert pedestal["node"] == model["metadata"]["roles"]["cap_top"]
    assert pedestal["H"] == -source[2]["inertia"]["pedestal"]["H"]
    assert pedestal["M"] == -source[2]["inertia"]["pedestal"]["M"]
    assert any(row["ends_reversed"] for row in model["metadata"]["correspondence"]["members"])


def test_zero_upper_height_merges_existing_roles_only():
    raw = example_input()
    raw["下部構造"]["寸法"]["高さ"]["H2"] = 0
    model = build(calculation(raw))
    assert len(model["nodes"]) == 6
    assert len(model["cases"][0]["member_loads"]) == 3
    assert sum(row["kind"] == 2 for row in model["elements"]) == 1


def test_dimensions_material_and_current_rebar_drive_new_model():
    raw = example_input()
    raw["下部構造"]["寸法"]["側面"]["B6"] = 2.8
    raw["下部構造"]["寸法"]["正面"]["W6"] = 4.6
    raw["下部構造"]["寸法"]["高さ"]["H4"] = 5.2
    column = raw["鉄筋"]["柱"]
    column["concrete_strength_mpa"] = 30
    column["materials"]["main"] = "SD345"
    column["main_rows"][0]["diameter_mm"] = 35
    model = build(calculation(raw))
    assert (model["section"]["width_mm"], model["section"]["height_mm"], model["section"]["fck"],
            model["section"]["Ec"], model["section"]["fyk"]) == (4600, 2800, 30, 28, 345)
    assert model["section"]["shear_span_mm"] == pytest.approx(7900)
    assert model["section"]["rebar"][0]["center_mm"] == 109.5
    assert model["section"]["rebar"][0]["diameter_mm"] == 35
    assert model["cases"][0]["member_loads"][0]["q_i"] == 315.56
    assert sum(row["length"] for row in model["elements"] if row["region"] in
               ("h4", "column_base_micro_member")) == pytest.approx(5.2)


@pytest.mark.parametrize("arrangement", ["outer_side", "between_layers", "same_row_extra"])
def test_native_main_rows_reject_side_bars_in_selected_rows(arrangement):
    raw = example_input()
    member = raw["鉄筋"]["柱"]
    if arrangement == "between_layers":
        inner = deepcopy(member["main_rows"][0])
        inner.update(layer=2, cover_mode="指定", center_mm=400, clear_gap_mm=260)
        member["main_rows"].insert(1, inner)
    else:
        side = member["main_rows"][1]
        side.update(center_mm=225, per_face_count=11)
        if arrangement == "same_row_extra":
            side["diameter_mm"] = 32
            side["distribution"].update(mode="両端＋中央ピッチ", edge_center_mm=108)
    geometry = rebar_model.section_geometry(raw, "柱")
    bars = rebar_model.column_layout(member, geometry)["bars"]
    rows = rebar_model.directional_rows(bars, "線路")
    # These are valid physical arrangements; native first/last-N selection is wrong.
    expected = {
        "outer_side": [(100, 19, 2), (108, 32, 29)],
        "between_layers": [(108, 32, 29), (350, 19, 2), (400, 32, 29)],
        "same_row_extra": [(108, 32, 31)],
    }[arrangement]
    assert [(row["center_mm"], row["diameter_mm"], row["count"])
            for row in rows[:len(expected)]] == expected
    with pytest.raises(InputError, match="先頭・末尾.*線路主筋"):
        build(calculation(raw))


def test_contiguous_two_main_layers_keep_two_native_layers():
    raw = example_input()
    member = raw["鉄筋"]["柱"]
    inner = deepcopy(member["main_rows"][0])
    inner.update(layer=2, cover_mode="指定", center_mm=200, clear_gap_mm=60)
    member["main_rows"].insert(1, inner)
    section = build(calculation(raw))["section"]
    assert section["main_face_layers"] == 2
    assert [(row["center_mm"], row["diameter_mm"], row["count"])
            for row in section["rebar"][:2] + section["rebar"][-2:]] == [
                (108, 32, 29), (200, 32, 29), (2500, 32, 29), (2592, 32, 29)]


def test_shared_corners_count_as_main_bars_once():
    raw = example_input()
    side = raw["鉄筋"]["柱"]["main_rows"][1]
    side.update(center_mm=108, diameter_mm=32, per_face_count=11)
    side["distribution"].update(mode="両端＋中央ピッチ", edge_center_mm=108)
    section = build(calculation(raw))["section"]
    assert section["main_face_layers"] == 1
    assert section["rebar"][0] == {"center_mm": 108, "diameter_mm": 32,
                                    "count": 29, "material": "SD390"}
    assert section["rebar"][-1] == {"center_mm": 2592, "diameter_mm": 32,
                                     "count": 29, "material": "SD390"}


def test_model_build_never_reads_saved_reports_or_samples(monkeypatch):
    source = calculation()
    def forbidden(*args, **kwargs):
        raise AssertionError("pure NDU builder attempted a file read")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    assert len(build(source)["nodes"]) == 7


def test_micro_remainder_at_tolerance_and_unbased_manual_positions_rejected():
    raw = example_input()
    raw["下部構造"]["寸法"]["高さ"]["H4"] = .01 + .5e-9
    with pytest.raises(InputError, match="1e-9 m"):
        build(calculation(raw))
    raw = example_input()
    raw["鉄筋"]["柱"]["position_mode"] = "指定"
    with pytest.raises(InputError, match="生成元"):
        build(calculation(raw))


@pytest.mark.parametrize("mutation,match", [
    (lambda raw, f, s: f["provenance"].update(input_sha256="0" * 64), "入力世代"),
    (lambda raw, f, s: f["short_term"].update(Ks=1), "short_term.Ks"),
    (lambda raw, f, s: f["foundation"].update(B=123), "foundation.B"),
    (lambda raw, f, s: s["frame"]["node_ids"].update(cap_top=2), "役割cap_top"),
    (lambda raw, f, s: s["frame"]["nodes"][1]["roles"].append("cap_top"), "役割cap_top"),
    (lambda raw, f, s: s["basic_cases"][6].update(load_type="incremental"), "EQL"),
    (lambda raw, f, s: s["combinations"][0]["coefficients"].__setitem__(7, 0), "組合せ"),
])
def test_mismatched_snapshots_roles_and_case_semantics_rejected(mutation, match):
    source = calculation()
    mutation(*source[:3])
    with pytest.raises(InputError, match=match):
        build(source)


@pytest.mark.parametrize("mutation,match", [
    (lambda member: member["main_rows"][0].update(per_face_count=None), "未完成"),
    (lambda member: member["main_rows"][1].update(material="SD345"), "混在"),
    (lambda member: member["column_hoops"]["direction_rows"][0].update(start_mm=0), "均一"),
])
def test_incomplete_or_unrepresentable_rebar_rejected(mutation, match):
    raw = example_input()
    mutation(raw["鉄筋"]["柱"])
    with pytest.raises(InputError, match=match):
        build(calculation(raw))
