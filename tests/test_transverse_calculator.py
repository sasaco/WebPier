"""Historical 0620 audit contracts plus public frame and input validation."""

from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path

import pytest

from src import calculate as calculate_foundation, parse_input
from src.inputs import InputError
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from legacy_reaction_oracle import load_legacy_reaction_oracle, parse_legacy_reaction_input, parse_legacy_foundation_input


PROJECT = Path(__file__).resolve().parents[1]
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = PROJECT / "tests" / "fixtures" / "baseline_input.json"
ORACLE = load_legacy_reaction_oracle("transverse_excel_oracle.json")


def calculate_audit(inputs, foundation, reactions):
    # Historical oracle fixtures contain the macro handoff, not normal 0500.
    return importlib.import_module("src.transverse_calculator").calculate_transverse_legacy(inputs, foundation, reactions)


def calculate_public(inputs, foundation, reactions):
    material_data = {"鉄筋": {part: {"concrete_strength_mpa": strength}
                           for part, strength in (("梁", 30), ("柱", 27), ("フーチング", 24))}}
    conditions = parse_longitudinal_design_conditions(material_data)
    return importlib.import_module("src.transverse_calculator").calculate_transverse(
        inputs, foundation, reactions, design_conditions=conditions,
    )


@pytest.fixture(scope="module")
def baseline():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    return data, inputs, calculate_foundation(parse_input(data)), calculate_reactions(inputs)


def test_transverse_frame_section_materials_and_normal_spring_handoff(baseline):
    _, inputs, foundation, reactions = baseline
    result = calculate_public(inputs, foundation, reactions)
    frame = result["frame"]
    assert result["schema_version"] == 2
    assert frame["model_version"] == 2
    assert [node["id"] for node in frame["nodes"]] == [1, 2, 3, 4, 5, 6]
    nodes = {node["id"]: node for node in frame["nodes"]}
    assert [nodes[frame["node_ids"][role]]["y"] for role in
            ("cap_top", "h2_h3", "h3_h4", "footing_top", "footing_centroid", "footing_bottom")] == pytest.approx([11.2, 10.025, 9.8, 2, 1, 0])
    assert [(member["id"], member["node_i"], member["node_j"])
            for member in frame["members"]] == [(1, 1, 5), (2, 5, 6), (3, 6, 2), (4, 2, 3), (5, 3, 4)]
    assert frame["sections"]["body"] == frame["section"]
    assert frame["section"]["area"] == 11.375
    assert frame["section"]["inertia"] == 40.04948
    assert {part: item["fck"] for part, item in frame["materials"].items()} == {
        "beam": 30, "column": 27, "footing": 24,
    }
    assert frame["materials"]["column"]["Ec"] == 26.5e6
    for member in frame["members"]:
        expected = (None if member["behavior"] == "rigid" else
                    "beam" if member["region"] in ("h2", "h3") else "column")
        assert member["material_ref"] == expected
    assert frame["support_node_id"] == 4
    for term in ("long_term", "short_term"):
        for spring in ("Kv", "Ks", "Kr"):
            source_component = "Kr_transverse" if spring == "Kr" else spring
            assert frame["springs"][term][spring] == foundation[term][source_component]
    assert frame["springs"]["short_term"]["Kr"] == 29872885
    assert frame["springs"]["short_term"]["Kr"] != foundation["macro_handoff_single"]["short_term"]["Kr"]
    assert frame["spring_provenance"]["direction"] == "transverse"


def test_components_use_transverse_single_centroids_without_moving_nodes(baseline):
    _, inputs, foundation, reactions = baseline
    reactions = deepcopy(reactions)
    reactions["macro_handoff_single"]["柱"]["xC"] = 0.625
    reactions["macro_handoff_single"]["フーチング"].update(N=10.0, xC=-0.125, xL=9.0, hG=1.125)
    reactions["macro_handoff_single"]["はり"].update(xC=0.375, xL=5.0)
    result = calculate_audit(inputs, foundation, reactions)
    frame, loads = result["cells"]["骨組図"], result["cells"]["荷重計算"]
    assert frame["M13"] == 0.625
    assert frame["L81"] == 1.125
    assert [frame[f"I{row}"] for row in range(79, 83)] == [0, 0, 0, 0]
    assert loads["P36"] == -0.125
    assert loads["V64"] == 0.375
    assert loads["AB36"] == -1.25


def test_s2_reaches_transverse_earthquake_and_preserves_other_loads(baseline: tuple) -> None:
    original, inputs, foundation, reactions = baseline
    data = deepcopy(original)
    for year, scale in ((2, 1), (10, 10), (30, 100)):
        key = f"雪荷重_{year}年確率"
        for side, point, outer, value in (("起点側", "B支点", "A支点", 123), ("終点側", "C支点", "D支点", 456)):
            branch = data["上部工反力"][side]
            branch[point]["支承"][9][key] = value * scale
            branch.setdefault(outer, {}).setdefault("合計", {})[key] = -7 * scale
    changed_inputs = parse_reaction_input(data)
    changed_reactions = calculate_reactions(changed_inputs)
    assert changed_reactions["snow_loads"]["points"]["C"]["雪荷重_30年確率"] == 45600
    assert changed_reactions["dead_loads"] == reactions["dead_loads"]
    before, after = calculate_audit(inputs, foundation, reactions), calculate_audit(changed_inputs, foundation, changed_reactions)
    assert before["input"].pop("snow") != after["input"].pop("snow")
    assert after["input"] == before["input"]
    for key in ("frame", "vertical", "inertia", "combinations"):
        assert after[key] == before[key]
    for index in (*range(6), 7):
        assert after["horizontal"][index] == before["horizontal"][index]
    assert after["horizontal_aggregates"][:3] == before["horizontal_aggregates"][:3]
    assert after["horizontal_aggregates"][4:] == before["horizontal_aggregates"][4:]
    handoff = changed_reactions["macro_handoff_single"]
    for side in ("B", "C"):
        assert after["horizontal"][6][side] == {"H": handoff["直角荷重強度"][6][f"R{side}"],
                                               "height": handoff["直角荷重位置"][6][f"R{side}"]}
    assert after["horizontal"][6] != before["horizontal"][6]
    earthquake = next(row for row in after["horizontal_aggregates"] if row["id"] == 7)
    assert earthquake["H"] == sum(after["horizontal"][6][side]["H"] for side in ("B", "C"))
    assert earthquake["M"] == sum(after["horizontal"][6][side]["H"] * after["horizontal"][6][side]["height"] for side in ("B", "C"))
    for old, new in zip(before["basic_cases"], after["basic_cases"]):
        if new["source_row"] == 32:
            assert new["loads"] == earthquake != old["loads"]
        else:
            assert new == old


def test_each_bearing_position_and_dead_load_detail_keeps_double_precision(baseline):
    _, inputs, foundation, _ = baseline
    b = tuple(replace(row, position=-2.123456789123 + i / 8,
                      d1=123.456789123 + i / 4, d2=12.3456789123 + i / 8)
              for i, row in enumerate(inputs.dead.b))
    c = tuple(replace(row, position=7.987654321987 + i / 8,
                      d1=98.7654321987 + i / 4, d2=9.87654321987 + i / 8)
              for i, row in enumerate(inputs.dead.c))
    inputs = replace(inputs, dead=replace(inputs.dead, b=b, c=c))
    reactions = calculate_reactions(inputs)
    cells = calculate_audit(inputs, foundation, reactions)["cells"]["荷重計算"]
    for index, (brow, crow) in enumerate(zip(b, c)):
        assert cells[f"G{5 + index}"] == brow.position
        assert cells[f"Y{5 + index}"] == crow.position
        assert cells[f"O{43 + index}"] == brow.d1
        assert cells[f"O{53 + index}"] == crow.d1
        assert cells[f"O{84 + index}"] == brow.d2
        assert cells[f"O{94 + index}"] == crow.d2
        # Both C-side dead-load tables reference B-side arms in the source.
        assert cells[f"V{53 + index}"] == brow.position
        assert cells[f"V{94 + index}"] == brow.position
        assert cells[f"V{53 + index}"] != crow.position


def test_unshared_train_moment_and_legacy_total_preserve_original_cell_ranges(baseline):
    _, inputs, foundation, reactions = baseline
    b = tuple(replace(row, position=2.0 if i == 0 else 0.0) for i, row in enumerate(inputs.dead.b))
    c = tuple(replace(row, position=7.0 if i == 0 else 0.0) for i, row in enumerate(inputs.dead.c))
    inputs = replace(inputs, dead=replace(inputs.dead, b=b, c=c))
    reactions = deepcopy(reactions)
    reactions["macro_handoff_single"]["列車荷重"]["安全性"]["複線"].update(RB=8.0, RC=12.0)
    cells = calculate_audit(inputs, foundation, reactions)["cells"]["荷重計算"]
    assert cells["V134"] == 4.0  # Distributed force: 8 * 0.5
    assert cells["Z134"] == 2.0
    assert cells["AD134"] == 16.0  # Source moment uses undistributed M134=8.
    assert cells["AD134"] != cells["V134"] * cells["Z134"]
    assert cells["AD144"] == 24.0  # C arm also uses B position 2, not C 7.
    # SUM(V134:AM153) includes distributed forces (20), arms (4), and
    # undistributed moments (40). This is a compatibility total, not a force.
    assert cells["V154"] == 64.0
    assert cells["AD154"] == 40.0


def test_all_eight_horizontal_force_and_height_pairs_use_upstream_singles(baseline):
    _, inputs, foundation, reactions = baseline
    cells = calculate_audit(inputs, foundation, reactions)["cells"]["荷重計算"]
    handoff = reactions["macro_handoff_single"]
    for index in range(8):
        for support, force_column, height_column in (("RB", "P", "T"), ("RC", "X", "AB")):
            assert cells[f"{force_column}{275 + index}"] == handoff["直角荷重強度"][index][support]
            assert cells[f"{height_column}{275 + index}"] == handoff["直角荷重位置"][index][support]
    assert cells["P275"] == 103.08000183105469
    assert cells["T275"] == 2.6419999599456787


def test_footing_inertia_uses_displaced_soil_density(baseline):
    _, inputs, foundation, reactions = baseline
    cells = calculate_audit(inputs, foundation, reactions)["cells"]["荷重計算"]
    assert cells["AB377"] == 500.5  # 1886.5 / 24.5 * (24.5 - 18)
    assert cells["AB32"] == 278.69  # Column line weight, B6 * W6 * 24.5.


@pytest.mark.parametrize("change", [
    {"unit_weight_footing": 0}, {"w6": 1e-5}, {"w6": 0.001, "b6": 1.0},
    {"w6": 1e150}, {"unit_weight_body": float("inf")},
])
def test_zero_density_rounded_zero_section_and_nonfinite_fail_as_input_error(baseline, change):
    _, inputs, foundation, reactions = baseline
    with pytest.raises(InputError):
        calculate_public(replace(inputs, geometry=replace(inputs.geometry, **change)), foundation, reactions)


def test_mismatched_upstream_hashes_fail_before_calculation(baseline):
    _, inputs, foundation, reactions = baseline
    foundation, reactions = deepcopy(foundation), deepcopy(reactions)
    foundation["provenance"]["input_sha256"] = "a" * 64
    reactions["provenance"]["input_sha256"] = "b" * 64
    with pytest.raises(InputError, match="SHA256"):
        calculate_public(inputs, foundation, reactions)


def test_schema_basic_row_identity_and_coefficient_dimensions_preserve_source(baseline):
    _, inputs, foundation, reactions = baseline
    originals = deepcopy(inputs), deepcopy(foundation), deepcopy(reactions)
    result = calculate_audit(inputs, foundation, reactions)
    assert result["schema_version"] == 1
    assert result["stage"] == "0620"
    assert {"骨組図", "荷重計算", "荷重図", "荷重組合せ"} == result["cells"].keys()
    assert result["input"]["geometry"]["w6"] == 6.5
    assert result["units"]["force"] == "kN"
    assert "0620" in result["provenance"]["source_workbook"]
    assert len(result["basic_cases"]) == 24
    assert len({row["id"] for row in result["basic_cases"]}) == 24
    assert [row["source_row"] for row in result["basic_cases"]] == list(range(11, 35))
    assert len(result["combinations"]) == 28
    assert all(len(column["coefficients"]) == 24 for column in result["combinations"])
    assert len({column["source_column"] for column in result["combinations"]}) == 28
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    assert (inputs, foundation, reactions) == originals


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case"])
def test_legacy_audit_all_transverse_cells_and_coefficients_match_independent_excel(case):
    result = calculate_audit(parse_legacy_reaction_input(case["input"]), case["upstream"]["foundation"], case["upstream"]["reactions"])
    for sheet, values in case["cells"].items():
        for address, expected in values.items():
            assert result["cells"][sheet][address] == expected, (sheet, address)
    actual_matrix = [[column["coefficients"][row] for column in result["combinations"]] for row in range(24)]
    assert actual_matrix == case["coefficient_matrix_rows_basic_cases"]


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case"])
def test_legacy_audit_each_source_transfer_preserves_value_or_documented_blank_normalization(case):
    result = calculate_audit(parse_legacy_reaction_input(case["input"]), **case["upstream"])
    actual = {(row["sheet"], row["cell"]): row for row in result["transfers"]}
    assert len(actual) == len(case["transferred"]) == 199
    normalized_cells = {f"O{row}" for row in (*range(43, 63), *range(84, 104))}
    normalized_cells |= {f"{column}{row}" for column in ("M", "AE") for row in range(5, 15)}
    for row in case["transferred"]:
        key = row["sheet"], row["address"]
        expected = row["value"]
        if expected is None and key[0] == "荷重計算" and key[1] in normalized_cells:
            expected = 0.0
        assert actual[key]["value"] == expected, key
        assert result["cells"][key[0]][key[1]] == expected, key
    assert "空D1/D2・分担率" in result["provenance"]["blank_normalization"]


@pytest.mark.parametrize("case", [case for case in ORACLE["cases"] if not case.get("upstream_is_synthetic")], ids=lambda case: case["case"])
def test_legacy_audit_complete_transverse_pipeline_matches_independent_excel(case):
    inputs = parse_legacy_reaction_input(case["input"])
    result = calculate_audit(inputs, calculate_foundation(parse_legacy_foundation_input(case["input"])), calculate_reactions(inputs))
    for sheet, values in case["cells"].items():
        for address, expected in values.items():
            assert result["cells"][sheet][address] == expected, (sheet, address)


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case"])
def test_legacy_audit_current_input_single_track_selection_matches_independent_single_loop(case):
    result = calculate_audit(parse_legacy_reaction_input(case["input"]), case["upstream"]["foundation"], case["upstream"]["reactions"])
    actual, expected = result["single_track_selection"], case["selection"]
    assert actual["evaluation_state"] == "current_input"
    assert actual["selected_index"] == expected["selected_index"]
    assert actual["key_score_single"] == expected["selected_score_single"]
    assert actual["MD1_single"] == expected["initial_single"]["MD1"]
    assert actual["MD2_single"] == expected["initial_single"]["MD2"]
    for a, e in zip(actual["candidates"], expected["candidates"]):
        assert a["sum_C_single"] == e["c_sum_single"]
        assert a["score_single"] == e["score_single"]
        assert a["winner_after"] == e["winner_after"]
    for side in ("B", "C"):
        assert list(actual[f"factors_{side}"]) == [0.0 if value is None else value for value in expected["final_factors"][side]]
    assert actual["fallback_to_d2"] == (expected["selected_index"] == 0)
    if expected["selected_index"] == 0:
        assert actual["source_row"] == "prior_D2"
        assert actual["source_unit"] == "kN"
        assert any("D2" in warning for warning in result["warnings"])
    assert "保存荷重" in result["provenance"]["selection_order"]


def test_duplicate_printed_numbers_have_unique_ids_and_uncomputed_rows_are_explicit(baseline):
    _, inputs, foundation, reactions = baseline
    result = calculate_audit(inputs, foundation, reactions)
    basics = result["basic_cases"]
    assert len({row["printed_number"] for row in basics}) < len(basics)
    assert len({column["printed_number"] for column in result["combinations"]}) < len(result["combinations"])
    for case in basics:
        if case["source_row"] in (17, 18, 19, 20, 21, 23, 24, 25, 26, 27):
            assert case["status"] == "template_row_only"
            assert "loads" not in case


def test_legacy_mixed_totals_are_separate_from_physical_force_sum(baseline):
    _, inputs, foundation, reactions = baseline
    result = calculate_audit(inputs, foundation, reactions)
    for group in ("train", "impact"):
        for table in result["vertical"][group].values():
            assert "N" not in table
            assert table["compatibility_total_unit"] is None
            assert table["distributed_force_sum"] == sum(row["N"] for row in table["rows"])
            assert table["arm_sum"] == sum(row["arm"] for row in table["rows"])
            assert table["source_moment_sum"] == result["cells"]["荷重計算"][f"AD{table['source_total_row']}"]
    assert all(row["status"] == "unconnected_source_load" for row in result["horizontal"][:3])


def test_legacy_audit_c_side_gate_rejects_positive_score_and_positive_b_factors():
    case = next(case for case in ORACLE["cases"] if case["case"] == "positive_score_c_zero")
    result = calculate_audit(parse_legacy_reaction_input(case["input"]), **case["upstream"])
    selection = result["single_track_selection"]
    assert selection["selected_index"] == 0
    for candidate in selection["candidates"]:
        assert candidate["sum_B_single"] == 1.0
        assert candidate["sum_C_single"] == 0.0
        assert candidate["score_single"] == 746.5899658203125
        assert candidate["eligible"] is False


@pytest.mark.parametrize("change", [{"b3": 0}, {"w3": 0}, {"b3": 0.01, "w3": 0.1}])
def test_positive_h1_invalid_section_fails_in_0620_only(baseline, change):
    _, inputs, foundation, _ = baseline
    inputs = replace(inputs, geometry=replace(inputs.geometry, h1=0.4, **change))
    reactions = calculate_reactions(inputs)
    with pytest.raises(InputError, match="0620.*geometry.*3"):
        calculate_public(inputs, foundation, reactions)
