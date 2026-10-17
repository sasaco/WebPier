"""0610 numerical contracts, independent arithmetic and upstream handoff routing."""

from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path

import pytest

from src import calculate as calculate_foundation, parse_input
from src.inputs import InputError
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from legacy_reaction_oracle import load_legacy_reaction_oracle, parse_legacy_reaction_input, parse_legacy_foundation_input


PROJECT = Path(__file__).resolve().parents[1]
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = PROJECT / "tests" / "fixtures" / "baseline_input.json"
ORACLE = load_legacy_reaction_oracle("longitudinal_excel_oracle.json")


def calculate(inputs, foundation, reactions):
    # Keep missing implementation a test failure, rather than a collection error.
    module = importlib.import_module("src.longitudinal_calculator")
    return module.calculate_longitudinal_legacy(inputs, foundation, reactions)


@pytest.fixture(scope="module")
def baseline():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    return data, inputs, calculate_foundation(parse_input(data)), calculate_reactions(inputs)


def test_frame_nodes_sections_and_transverse_single_springs(baseline):
    _, inputs, foundation, reactions = baseline
    result = calculate(inputs, foundation, reactions)
    cells = result["cells"]["骨組図"]
    frame = result["frame"]
    assert frame["model_version"] == 2
    assert [node["id"] for node in frame["nodes"]] == [1, 2, 3, 4, 5, 6]
    nodes = {node["id"]: node for node in frame["nodes"]}
    assert [nodes[frame["node_ids"][role]]["y"] for role in
            ("cap_top", "h2_h3", "h3_h4", "footing_top", "footing_centroid", "footing_bottom")] == pytest.approx([11.2, 10.025, 9.8, 2, 1, 0])
    assert [(member["id"], member["node_i"], member["node_j"])
            for member in frame["members"]] == [(1, 1, 5), (2, 5, 6), (3, 6, 2), (4, 2, 3), (5, 3, 4)]
    assert frame["sections"]["body"] == frame["section"]
    assert frame["materials"]["body"]["fck"] == 24
    assert frame["support_node_id"] == 4
    assert frame["legacy_nodes"] == [{"id": row - 80, "x": cells[f"I{row}"], "y": cells[f"L{row}"],
                                     "source_row": row, "active_node_id": row - 80} for row in range(81, 85)]
    assert [cells[f"I{row}"] for row in range(81, 85)] == [0, 0, 0, 0]
    assert [cells[f"L{row}"] for row in range(81, 85)] == pytest.approx([11.2, 2, 1, 0])
    # 6.5 * 1.75 = 11.375; 6.5 * 1.75**3 / 12 = 2.9029947916...
    assert cells["AB93"] == 11.375
    assert cells["AB94"] == 2.90299
    for column, term in (("L", "long_term"), ("T", "short_term")):
        for row, spring in ((144, "Kv"), (145, "Ks"), (146, "Kr")):
            assert cells[f"{column}{row}"] == foundation["macro_handoff_single"][term][spring]
    assert cells["T146"] == 29872884
    assert cells["T146"] != foundation["short_term"]["Kr_transverse"]
    assert cells["T146"] != foundation["short_term"]["Kr_longitudinal"]


def test_shape_eccentricity_does_not_move_frame_nodes(baseline):
    _, inputs, foundation, reactions = baseline
    handoff = deepcopy(reactions)
    handoff["macro_handoff_single"]["柱"]["xL"] = 0.625
    handoff["macro_handoff_single"]["フーチング"]["hG"] = 1.125
    cells = calculate(inputs, foundation, handoff)["cells"]["骨組図"]
    assert [cells[f"I{row}"] for row in range(81, 85)] == [0, 0, 0, 0]
    assert cells["L83"] == 1.125


def test_explicit_asymmetric_support_positions_reach_longitudinal_load_arms(baseline):
    original, _, foundation, _ = baseline
    data = deepcopy(original)
    data["上部構造"]["起点側"]["桁長"]["L2"] = 0.575
    data["上部構造"]["終点側"]["桁長"]["L1"] = 0.375
    data["上部構造"]["起点側"]["支承位置_f"] = 0.4
    data["上部構造"]["終点側"]["支承位置_f"] = 0.55
    inputs = parse_reaction_input(data)
    cells = calculate(inputs, foundation, calculate_reactions(inputs))["cells"]["荷重計算"]
    assert (cells["E5"], cells["E6"]) == (0.4, 0.55)
    assert (cells["T29"], cells["T30"]) == (-0.4, 0.55)


def test_snow_reaches_longitudinal_horizontal_and_s30_vertical_loads(baseline: tuple) -> None:
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
    assert changed_reactions["snow_loads"]["points"]["B"]["雪荷重_30年確率"] == 12300
    assert changed_reactions["snow_loads"]["points"]["C"]["雪荷重_30年確率"] == 45600
    assert changed_reactions["dead_loads"] == reactions["dead_loads"]
    before, after = calculate(inputs, foundation, reactions), calculate(changed_inputs, foundation, changed_reactions)
    assert before["input"].pop("snow") != after["input"].pop("snow")
    assert after["input"] == before["input"]
    for key in ("frame", "inertia", "combinations"):
        assert after[key] == before[key]
    assert {key: value for key, value in after["vertical"].items() if key != "snow30"} == {
        key: value for key, value in before["vertical"].items() if key != "snow30"}
    snow = after["vertical"]["snow30"]
    for side, force, arm, moment in (("B", 12300, -changed_inputs.spans.b.f, -4612.5),
                                    ("C", 45600, changed_inputs.spans.c.f, 17100.0)):
        assert snow[side] == {"N": force, "arm": arm, "M": moment}
    assert snow["N"] == 57900
    assert snow["M"] == 12487.5
    for result, upstream in ((before, reactions), (after, changed_reactions)):
        handoff = upstream["macro_handoff_single"]
        for row, expected in zip(result["horizontal"], [*handoff["線路荷重強度"], *handoff["線路雪荷重強度"]]):
            assert (row["B"], row["C"], row["total"]) == (expected["RB"], expected["RC"], expected["RB"] + expected["RC"])
    assert after["horizontal"][8] != before["horizontal"][8]
    assert after["basic_cases"][21]["loads"] == snow != before["basic_cases"][21]["loads"]
    assert after["basic_cases"][22]["loads"] == after["horizontal"][10]
    assert after["basic_cases"][23]["loads"] == after["horizontal"][11]


def test_baseline_dead_load_and_displaced_soil_equations(baseline):
    _, inputs, foundation, reactions = baseline
    cells = calculate(inputs, foundation, reactions)["cells"]["荷重計算"]
    assert cells["AB18"] == 278.69  # ROUND(1.75 * 6.5 * 24.5, 2)
    assert cells["M29"] == 890
    assert cells["M30"] == 840
    # ROUND(890 + 840 + 0 + 616.9400024414062 - 278.69 * 1.4, 2)
    assert cells["AB35"] == 1956.77
    assert cells["AB36"] == -18.75  # -890 * 0.375 + 840 * 0.375
    assert cells["AB22"] == 0
    assert cells["AB170"] == 500.5  # 1886.5 / 24.5 * (24.5 - 18)


def test_each_eccentric_moment_rounds_before_summing_and_uses_single_handoff(baseline):
    _, inputs, foundation, reactions = baseline
    inputs = replace(inputs, spans=replace(inputs.spans,
        b=replace(inputs.spans.b, f=0), c=replace(inputs.spans.c, f=0)))
    handoff = deepcopy(reactions)
    # Controlled exact dependency values isolate rounding and routing. Display
    # weights remain unchanged, so substituting them for the handoff fails.
    handoff["macro_handoff_single"]["桁受け"].update(N=1.0, xL=0.125)
    handoff["macro_handoff_single"]["はり"].update(N=1.0, xL=0.125)
    handoff["macro_handoff_single"]["フーチング"].update(N=10.0, xL=-0.125)
    cells = calculate(inputs, foundation, handoff)["cells"]["荷重計算"]
    assert cells["AB36"] == 0.26  # ROUND(.125, 2) + ROUND(.125, 2)
    assert cells["AB22"] == -1.25
    assert cells["AB35"] == 1341.83


def test_dead_reaction_totals_ignore_input_cache_and_remain_double(baseline):
    original, _, foundation, _ = baseline
    data = deepcopy(original)
    b = data["上部工反力"]["起点側"]["B支点"]
    c = data["上部工反力"]["終点側"]["C支点"]
    b["支承"][0]["固定死荷重_D1"] = 123.456789123
    b["支承"][1]["固定死荷重_D1"] = 0.25
    c["支承"][0]["固定死荷重_D1"] = 45.678912345
    c["支承"][1]["固定死荷重_D1"] = 0.5
    b["合計"] = {"固定死荷重_D1": 999999}
    c["合計"] = {"固定死荷重_D1": 888888}
    inputs = parse_reaction_input(data)
    reactions = calculate_reactions(inputs)
    cells = calculate(inputs, foundation, reactions)["cells"]["荷重計算"]
    assert cells["M29"] == 123.706789123
    assert cells["M30"] == 46.178912345


def test_all_ten_horizontal_forces_use_single_handoff_without_sum_rounding(baseline):
    _, inputs, foundation, reactions = baseline
    cells = calculate(inputs, foundation, reactions)["cells"]["荷重計算"]
    for row, forces in enumerate(reactions["macro_handoff_single"]["線路荷重強度"], 131):
        assert cells[f"U{row}"] == forces["RB"]
        assert cells[f"Y{row}"] == forces["RC"]
        assert cells[f"AC{row}"] == forces["RB"] + forces["RC"]
    assert cells["AC131"] == 215.1500015258789
    assert cells["AC131"] != 215.15


def test_zero_footing_density_is_rejected_before_division(baseline):
    _, inputs, foundation, reactions = baseline
    inputs = replace(inputs, geometry=replace(inputs.geometry, unit_weight_footing=0))
    with pytest.raises(InputError):
        calculate(inputs, foundation, reactions)


@pytest.mark.parametrize("change", [{"b6": 1e150}, {"unit_weight_body": float("inf")}])
def test_nonfinite_or_overflow_is_input_error(baseline, change):
    _, inputs, foundation, reactions = baseline
    inputs = replace(inputs, geometry=replace(inputs.geometry, **change))
    with pytest.raises(InputError):
        calculate(inputs, foundation, reactions)


def test_result_schema_is_traceable_and_json_finite(baseline):
    _, inputs, foundation, reactions = baseline
    original_foundation, original_reactions = deepcopy(foundation), deepcopy(reactions)
    result = calculate(inputs, foundation, reactions)
    assert result["schema_version"] == 1
    assert result["stage"] == "0610"
    assert {"骨組図", "荷重計算", "荷重図", "荷重組合せ"} <= result["cells"].keys()
    assert result["input"]["geometry"]["b6"] == inputs.geometry.b6
    assert result["units"]["force"] == "kN"
    assert "0610" in result["provenance"]["source_workbook"]
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    assert foundation == original_foundation
    assert reactions == original_reactions


def test_mismatched_upstream_input_hashes_are_rejected(baseline):
    _, inputs, foundation, reactions = baseline
    foundation, reactions = deepcopy(foundation), deepcopy(reactions)
    foundation["provenance"]["input_sha256"] = "a" * 64
    reactions["provenance"]["input_sha256"] = "b" * 64
    with pytest.raises(InputError, match="SHA256"):
        calculate(inputs, foundation, reactions)


@pytest.mark.parametrize("change", [{"b6": 1e-5}, {"b6": 0.001, "w6": 1.0}])
def test_rounded_zero_section_is_rejected(baseline, change):
    _, inputs, foundation, reactions = baseline
    with pytest.raises(InputError, match="断面"):
        calculate(replace(inputs, geometry=replace(inputs.geometry, **change)), foundation, reactions)


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case"])
def test_all_original_cells_match_independent_excel_with_minimal_upstream(case):
    inputs = parse_legacy_reaction_input(case["input"])
    result = calculate(inputs, case["upstream"]["foundation"], case["upstream"]["reactions"])
    for transferred in case["transferred"]:
        assert result["cells"][transferred["sheet"]][transferred["address"]] == transferred["value"]
    for sheet, expected_cells in case["cells"].items():
        for address, expected in expected_cells.items():
            actual = result["cells"][sheet][address]
            # Excel and Python differ by one ULP only when these four already
            # rounded moments are summed in the signed synthetic interface case.
            if case["case"] == "signed_handoff_boundaries" and sheet == "荷重計算" and address in {"Y33", "AB36"}:
                assert actual == pytest.approx(expected, rel=0, abs=1e-12), (sheet, address)
            else:
                assert actual == expected, (sheet, address)
    assert [basic["source_row"] for basic in result["basic_cases"]] == list(range(11, 32))
    assert [basic["spring_case"] for basic in result["basic_cases"]] == [
        1, 1, 1, 1, 1, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3]
    actual_matrix = [[column["coefficients"][row] for column in result["combinations"]] for row in range(21)]
    assert actual_matrix == case["coefficient_matrix_rows_basic_cases"]


@pytest.mark.parametrize("case", ORACLE["cases"][:7], ids=lambda case: case["case"])
def test_complete_pipeline_matches_independent_excel(case):
    from reaction_combination_oracle import combination_expectations

    reaction_cases = load_legacy_reaction_oracle("reaction_excel_oracle.json")["cases"]
    reaction_name = "current_input" if case["case"] == "double_precision_units" else case["case"]
    reaction_case = next(row for row in reaction_cases if row["case"] == reaction_name)
    if case["case"] == "double_precision_units":
        # Reuse only the independently identical train/LR/B evidence; geometry,
        # density, bearing arms and D1/D2 remain this case's own inputs.
        structure, reference = case["input"]["上部構造"], reaction_case["input"]["上部構造"]
        assert structure["列車"] == reference["列車"]
        assert structure["支承データ"] == reference["支承データ"]
        for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
            for field in ("桁長", "衝撃係数"):
                assert structure[side][field] == reference[side][field]
            assert [row["列車分担"] for row in case["input"]["上部工反力"][side][point]["支承"]] == [
                row["列車分担"] for row in reaction_case["input"]["上部工反力"][side][point]["支承"]]
    expected_cells_by_sheet = deepcopy(case["cells"])
    revised = combination_expectations(reaction_case, case["input"])
    for index, forces in enumerate(revised["single"]):
        expected_cells_by_sheet["荷重計算"].update({f"U{131 + index}": forces["RB"],
                                                f"Y{131 + index}": forces["RC"],
                                                f"AC{131 + index}": forces["RB"] + forces["RC"]})
    inputs = parse_legacy_reaction_input(case["input"])
    result = calculate(inputs, calculate_foundation(parse_legacy_foundation_input(case["input"])), calculate_reactions(inputs))
    for sheet, expected_cells in expected_cells_by_sheet.items():
        for address, expected in expected_cells.items():
            assert result["cells"][sheet][address] == expected, (sheet, address)


def test_zero_actions_and_signed_arms_remain_linked_to_basic_cases(baseline):
    _, inputs, foundation, reactions = baseline
    reactions = deepcopy(reactions)
    for side in ("B", "C"):
        reactions["dead_loads"]["points"][side]["D2"] = 0
    for forces in reactions["macro_handoff_single"]["線路荷重強度"]:
        forces.update(RB=0.0, RC=0.0)
    for forces in reactions["macro_handoff_single"]["線路雪荷重強度"]:
        forces.update(RB=0.0, RC=0.0)
    result = calculate(inputs, foundation, reactions)
    assert result["vertical"]["additional"]["top"]["N"] == 0
    assert result["vertical"]["additional"]["top"]["M"] == 0
    assert result["cells"]["荷重計算"]["T52"] < 0
    assert result["cells"]["荷重計算"]["T53"] > 0
    assert all(case["loads"]["total"] == 0 for case in result["basic_cases"][9:17])
    assert all(case["loads"]["total"] == 0 for case in result["basic_cases"][22:24])
    assert [case["id"] for case in result["combinations"] if case["scope"] == "body"] == list(range(1, 15))
    assert [case["id"] for case in result["combinations"] if case["scope"] == "foundation"] == list(range(1, 11))


def test_standalone_stage_preserves_upstream_warnings(baseline):
    _, inputs, foundation, reactions = baseline
    foundation, reactions = deepcopy(foundation), deepcopy(reactions)
    foundation["warnings"] = ["支持層のその他分岐"]
    reactions["warnings"] = ["H3=0のゼロ体積拡張"]
    result = calculate(inputs, foundation, reactions)
    assert "0500: 支持層のその他分岐" in result["warnings"]
    assert "0600: H3=0のゼロ体積拡張" in result["warnings"]


@pytest.mark.parametrize("change", [{"b3": 0}, {"w3": 0}, {"b3": 0.01, "w3": 0.1}])
def test_positive_h1_invalid_section_fails_in_0610_only(baseline, change):
    _, inputs, foundation, _ = baseline
    inputs = replace(inputs, geometry=replace(inputs.geometry, h1=0.4, **change))
    reactions = calculate_reactions(inputs)  # 0600 keeps its zero-volume compatibility
    with pytest.raises(InputError, match="0610.*geometry.*3"):
        calculate(inputs, foundation, reactions)
