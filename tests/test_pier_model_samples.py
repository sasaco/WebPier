"""Reusable complete inputs and independently fixed physical frame expectations."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src import calculate as calculate_foundation, parse_input
from src.longitudinal_calculator import calculate_longitudinal, calculate_longitudinal_legacy
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.transverse_calculator import calculate_transverse, calculate_transverse_legacy


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = FIXTURES / "pier_models"
EXPECTATIONS = json.loads((SAMPLES / "expectations.json").read_text(encoding="utf-8"))
SAMPLE_CASES = (
    ("parapet-asymmetric.json", "pedestal_nonzero", "parapet_asymmetric"),
    ("asymmetric-footing.json", "geometry_water", "asymmetric_footing"),
)


def oracle_case(filename, name):
    oracle = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return next(case for case in oracle["cases"] if case["case"] == name)


def assert_frame_matches_expected(frame, expected):
    observed = deepcopy({key: frame[key] for key in expected})
    # Literal decimal heights allow only ordinary float addition residuals.
    # IDs, x (including 1e-12 eccentricity), roles and every reference are exact.
    for key in ("nodes", "legacy_nodes"):
        for node, literal in zip(observed[key], expected[key], strict=True):
            assert node["y"] == pytest.approx(literal["y"], rel=0, abs=4e-15)
            node["y"] = literal["y"]
    assert observed == expected


@pytest.mark.parametrize("filename,source_case,expected_case", SAMPLE_CASES)
def test_complete_sample_preserves_original_independent_numeric_input(filename, source_case, expected_case):
    sample = json.loads((SAMPLES / filename).read_text(encoding="utf-8"))
    original = oracle_case("reaction_excel_oracle.json", source_case)["input"]
    annotation = sample["出典"].pop("モデル検証サンプル")
    assert sample == original
    assert annotation["元ケース"] == source_case
    assert annotation["種類"] == "独立試験条件からの変更サンプル"
    assert "原PDFの実測値ではない" in annotation["注意"]
    assert EXPECTATIONS["cases"][expected_case]["input_fixture"] == filename


@pytest.mark.parametrize("filename,source_case,expected_case", SAMPLE_CASES)
def test_samples_build_both_physical_graphs_without_changing_independent_weights(filename, source_case, expected_case):
    sample = json.loads((SAMPLES / filename).read_text(encoding="utf-8"))
    before = deepcopy(sample)
    inputs = parse_reaction_input(sample)
    foundation = calculate_foundation(parse_input(sample))
    reactions = calculate_reactions(inputs)
    independent = oracle_case("reaction_excel_oracle.json", source_case)
    # Stored A/D snapshots now are explicit input. Compare geometry/selfweight
    # against the original independent oracle without erasing those inputs.
    for component in ("桁受け", "はり", "柱", "フーチング", "上載土", "高水位", "平水位", "低水位"):
        assert reactions["macro_handoff_single"][component] == independent["public_single"][component]
    for direction, calculator, oracle_name in (
        ("b", calculate_longitudinal, "longitudinal_excel_oracle.json"),
        ("w", calculate_transverse, "transverse_excel_oracle.json"),
    ):
        conditions = parse_longitudinal_design_conditions({
            "鉄筋": {part: {"concrete_strength_mpa": strength}
                   for part, strength in (("梁", 30), ("柱", 27), ("フーチング", 24))},
        })
        result = calculator(inputs, foundation, reactions, design_conditions=conditions)
        frame = result["frame"]
        expected = deepcopy(EXPECTATIONS["cases"][expected_case]["directions"][direction])
        # Physical graph expectations stay fixed; only the approved
        # material references now distinguish existing input parts.
        for member in expected.get("members", []):
            member["material_ref"] = (None if member["behavior"] == "rigid" else
                                      "beam" if member["region"] in ("h2", "h3") else "column")
        assert_frame_matches_expected(frame, expected)
        old = oracle_case(oracle_name, source_case)
        # Public graphs use normal springs. The old cell oracle is an explicit
        # Single-handoff audit and remains unchanged.
        audit_result = (calculate_transverse_legacy(inputs, foundation, reactions)
                        if direction == "w" else calculate_longitudinal_legacy(inputs, foundation, reactions))
        expected_cells = old["cells"]["骨組図"]
        assert {key: audit_result["cells"]["骨組図"][key] for key in expected_cells} == expected_cells
        assert frame["load_anchors"]["pedestal"]["automatic_self_weight"] is False
        nodes = {node["id"]: node for node in frame["nodes"]}
        line = frame["load_anchors"]["column_line_load"]
        members = {member["id"]: member for member in frame["members"]}
        spans = [(nodes[members[mid]["node_j"]]["y"], nodes[members[mid]["node_i"]]["y"])
                 for mid in line["member_ids"]]
        lower, upper = nodes[line["to_node_id"]]["y"], nodes[line["from_node_id"]]["y"]
        # Unit distributed load: splitting conserves both force and first
        # moment about the base; H1/rigid arm never enter this old interval.
        assert sum(hi - lo for lo, hi in spans) == pytest.approx(upper - lower)
        assert sum((hi * hi - lo * lo) / 2 for lo, hi in spans) == pytest.approx((upper * upper - lower * lower) / 2)
        assert frame["load_anchors"]["cap_top"]["node_id"] == frame["node_ids"]["cap_top"]
        if "parapet_top" in frame["node_ids"]:
            assert frame["node_ids"]["parapet_top"] != frame["node_ids"]["cap_top"]
    assert sample == before


def test_parapet_sample_retains_excel_selfweight_and_single_handoff_once():
    data = json.loads((SAMPLES / "parapet-asymmetric.json").read_text(encoding="utf-8"))
    reactions = calculate_reactions(parse_reaction_input(data))
    assert reactions["cells"]["橋脚自重"]["X64"] == 5.29
    assert reactions["macro_handoff_single"]["桁受け"]["N"] == 5.289999961853027
    assert reactions["macro_handoff_single"]["桁受け"]["N"] != 5.29
