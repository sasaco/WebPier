"""Normal transverse springs are independent of canonical actions and old audit."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pytest

from src.calculator import calculate as calculate_foundation
from src.inputs import InputError, parse_input
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input


BASELINE = Path(__file__).parent / "fixtures" / "baseline_input.json"
SPRING_CELLS = {"L142", "L143", "L144", "T142", "T143", "T144"}
EXPECTED_TERMS = {
    "long_term": {"Kv": 16777217, "Ks": 16777219, "Kr": 86320647},
    "short_term": {"Kv": 33554435, "Ks": 33554437, "Kr": 172641294},
}


def calculate_public(inputs, foundation, reactions):
    return importlib.import_module("src.transverse_calculator").calculate_transverse(
        inputs, foundation, reactions,
        design_conditions=parse_longitudinal_design_conditions({
            "鉄筋": {part: {"concrete_strength_mpa": 27} for part in ("梁", "柱", "フーチング")},
        }),
    )


def calculate_legacy(inputs, foundation, reactions):
    # Planned API imports only when a test executes, never during collection.
    return importlib.import_module("src.transverse_calculator").calculate_transverse_legacy(
        inputs, foundation, reactions,
    )


@pytest.fixture(scope="module")
def calculated_upstream():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    return data, inputs, calculate_foundation(parse_input(data)), calculate_reactions(inputs)


@pytest.fixture
def source(calculated_upstream):
    data, inputs, foundation, reactions = deepcopy(calculated_upstream)
    # All six normal values differ from the macro and exercise exact Double
    # handoff. Longitudinal Kr is also distinct to detect a direction mix-up.
    foundation["long_term"].update(
        Kv=16777217, Ks=16777219, Kr_transverse=86320647, Kr_longitudinal=52218663,
    )
    foundation["short_term"].update(
        Kv=33554435, Ks=33554437, Kr_transverse=172641294, Kr_longitudinal=104437326,
    )
    foundation["macro_handoff_single"] = {
        "long_term": {"Kv": 10101, "Ks": 10102, "Kr": 10103},
        "short_term": {"Kv": 20201, "Ks": 20202, "Kr": 20203},
    }
    return data, inputs, foundation, reactions


def expected_components():
    return [
        {
            "direction": "transverse", "term": term, "component": component,
            "value": value,
            "source_path": f"0500.{term}.{'Kr_transverse' if component == 'Kr' else component}",
            "precision": "Double", "unit": "kN·m/rad" if component == "Kr" else "kN/m",
        }
        for term, values in EXPECTED_TERMS.items()
        for component, value in values.items()
    ]


def test_public_0620_routes_all_six_normal_transverse_springs(source):
    _, inputs, foundation, reactions = source
    result = calculate_public(inputs, foundation, reactions)
    assert result["frame"]["springs"] == EXPECTED_TERMS
    provenance = result["frame"]["spring_provenance"]
    by_component = {(row["term"], row["component"]): row for row in provenance["components"]}
    assert len(by_component) == 6
    for expected in expected_components():
        assert by_component[expected["term"], expected["component"]] == expected


def test_public_0620_records_direction_support_node_and_normal_dependencies(source):
    _, inputs, foundation, reactions = source
    result = calculate_public(inputs, foundation, reactions)
    frame = result["frame"]
    provenance = frame["spring_provenance"]
    assert provenance["direction"] == "transverse"
    assert provenance["support_node_id"] == frame["support_node_id"]
    assert len(provenance["components"]) == 6
    sort_key = lambda row: (row["term"], row["component"])
    assert sorted(provenance["components"], key=sort_key) == sorted(expected_components(), key=sort_key)
    # These source paths are authoritative; top-level provenance may also name
    # material/raw reaction dependencies introduced by the canonical model.
    assert all(row["source_path"].startswith("0500.") for row in provenance["components"])
    assert all("macro_handoff_single" not in row["source_path"] for row in provenance["components"])


def legacy_without_spring_cells(result):
    """Old audit values may change only at their historical spring handoff."""
    result = deepcopy(result)
    for cell in SPRING_CELLS:
        result["cells"]["骨組図"].pop(cell)
    result["transfers"] = [row for row in result["transfers"]
                           if not (row["sheet"] == "骨組図" and row["cell"] in SPRING_CELLS)]
    result["frame"].pop("springs")
    return result


def test_normal_spring_changes_leave_all_canonical_actions_and_definitions_unchanged(source):
    _, inputs, foundation, reactions = source
    current = calculate_public(inputs, foundation, reactions)
    changed = deepcopy(foundation)
    for term in ("long_term", "short_term"):
        for component in ("Kv", "Ks", "Kr_transverse"):
            changed[term][component] += 123
    updated = calculate_public(inputs, changed, reactions)
    assert current["frame"]["springs"] != updated["frame"]["springs"]
    for key in ("actions", "basic_cases", "define_cases", "combinations", "extraction_cases"):
        assert current[key] == updated[key]
    for key in ("nodes", "members", "sections", "materials", "load_anchors"):
        assert current["frame"][key] == updated["frame"][key]


def test_legacy_reads_macro_springs_and_preserves_all_other_audit_values(source):
    _, inputs, foundation, reactions = source
    legacy = calculate_legacy(inputs, foundation, reactions)
    changed = deepcopy(foundation)
    for term in ("long_term", "short_term"):
        for component in ("Kv", "Ks", "Kr"):
            changed["macro_handoff_single"][term][component] += 7
    updated = calculate_legacy(inputs, changed, reactions)
    assert legacy["frame"]["springs"] == foundation["macro_handoff_single"]
    assert updated["frame"]["springs"] == changed["macro_handoff_single"]
    assert legacy_without_spring_cells(legacy) == legacy_without_spring_cells(updated)
    # The public calculation does not depend on the obsolete macro values.
    assert calculate_public(inputs, foundation, reactions) == calculate_public(inputs, changed, reactions)


@pytest.mark.parametrize("term", ["long_term", "short_term"])
@pytest.mark.parametrize("component", ["Kv", "Ks", "Kr_transverse"])
def test_public_0620_missing_normal_spring_does_not_fall_back_to_macro(source, term, component):
    _, inputs, foundation, reactions = source
    del foundation[term][component]
    original = deepcopy(source)
    with pytest.raises(InputError, match=re.escape(f"0500.{term}.{component}")):
        calculate_public(inputs, foundation, reactions)
    assert source == original


@pytest.mark.parametrize("macro_state", ["missing", "nan", "inf"])
def test_public_0620_does_not_read_missing_or_poisoned_foundation_macro(source, macro_state):
    _, inputs, foundation, reactions = source
    expected = calculate_public(inputs, foundation, reactions)
    changed = deepcopy(foundation)
    if macro_state == "missing":
        del changed["macro_handoff_single"]
    else:
        changed["macro_handoff_single"] = {
            "long_term": {"Kv": float(macro_state), "Ks": float(macro_state), "Kr": float(macro_state)},
            "short_term": {"Kv": float(macro_state), "Ks": float(macro_state), "Kr": float(macro_state)},
        }
    result = calculate_public(inputs, changed, reactions)
    assert result["frame"]["springs"] == EXPECTED_TERMS
    assert result == expected


def test_public_and_legacy_calculation_do_not_mutate_inputs_or_upstream_results(source):
    original = deepcopy(source)
    _, inputs, foundation, reactions = source
    calculate_public(inputs, foundation, reactions)
    assert source == original
    calculate_legacy(inputs, foundation, reactions)
    assert source == original


def test_public_0620_pdf_prints_normal_values_and_engineering_direction(source, tmp_path):
    _, inputs, foundation, reactions = source
    result = calculate_public(inputs, foundation, reactions)
    original = deepcopy(result)
    path = tmp_path / "0620-normal-transverse-springs.pdf"
    renderer = importlib.import_module("src.transverse_report")
    renderer.render_transverse_report(result, path)
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    for values in EXPECTED_TERMS.values():
        for value in values.values():
            assert f"{value:,}" in text
    compact = "".join(text.split())
    assert "線路直角方向" in compact
    assert "Double" not in compact
    assert "Single" not in compact
    assert "0610のKrは0500直角方向" not in compact
    assert "計算済みSingle値" not in compact
    assert result == original
