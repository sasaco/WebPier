"""Independent native expansion of all resolved states and fixed case meanings."""

from copy import deepcopy
import json

import pytest

from src.frameweb_export import build_frameweb_input, validate_frameweb_input
from src.inputs import InputError
from test_frameweb_export import FIXTURES, canonical_input, current_result


def _add(vector, key, value):
    vector[key] = vector.get(key, 0) + value


def canonical_vector(source, variant):
    """Read canonical load families without invoking exporter helpers."""
    vector = {}
    anchors = source["frame"]["load_anchors"]
    for row in variant["resolved_components"]:
        identifier, values = row["basic_case_id"], row["loads"]
        spring = source["basic_cases"][identifier - 1]["spring_case"]
        if identifier == 1:
            positions = (("cap_top", values["top"]), ("footing_centroid", values["footing"]))
            for member in anchors["column_line_load"]["member_ids"]:
                _add(vector, (spring, "member", str(member), "gy"), -values["column"]["intensity"])
        elif identifier == 2:
            positions = (("cap_top", values["top"]), ("footing_centroid", values["soil"]))
        elif identifier <= 12:
            positions = (("footing_centroid" if identifier <= 5 else "cap_top", values),)
        else:
            _add(vector, (spring, "node", str(anchors["cap_top"]["node_id"]), "tx"), values["total"])
            positions = ()
        for role, load in positions:
            node = str(anchors[role]["node_id"])
            for component, value in (("ty", -load["N"]), ("rz", -load["M"])):
                _add(vector, (spring, "node", node, component), value)
    return {key: value for key, value in vector.items() if value}


def native_vector(native, combination, sign):
    vector = {}
    for column, factor in native["combine"][str(combination)].items():
        if not column.startswith("C"):
            continue
        define = native["define"][column[1:]]
        case_id = define.get("C2", define["C1"]) if sign < 0 else define["C1"]
        case = native["load"][str(abs(case_id))]
        factor *= 1 if case_id > 0 else -1
        for row in case.get("load_node", []):
            for component in ("tx", "ty", "rz"):
                _add(vector, (case["fix_node"], "node", row["n"], component), factor * (row[component] or 0))
        for row in case.get("load_member", []):
            assert row["m1"] == row["m2"] and row["P1"] == row["P2"]
            _add(vector, (case["fix_node"], "member", row["m1"], row["direction"]), factor * row["P1"])
    return {key: value for key, value in vector.items() if value}


def assert_all_vectors(source, native):
    count = 0
    for combination in source["combinations"]:
        for variant in combination["variants"]:
            expected = canonical_vector(source, variant)
            actual = native_vector(native, combination["id"], variant["horizontal_sign"])
            assert actual.keys() == expected.keys()
            for key, value in expected.items():
                assert abs(actual[key] - value) <= 1e-10 + 1e-12 * max(abs(actual[key]), abs(value))
            count += 1
    assert count == 28


def test_all_current_auxiliary_values_320_nominal_coefficients_and_28_states(current_result):
    exported = build_frameweb_input(current_result)
    native = exported.document
    webpier = json.loads((FIXTURES / "frameweb_webpier_reference.json").read_text(encoding="utf-8"))
    example = json.loads((FIXTURES / "frameweb_example2_mapping.json").read_text(encoding="utf-8"))
    matrix = list(map(list, zip(*(row["coefficients"] for row in current_result["combinations"]), strict=True)))
    assert matrix == example["coefficient_matrix"]["values"]
    assert len(native["load"]) == len(native["define"]) == 28
    assert len(native["combine"]) == 16 and len(native["pickup"]) == 8
    for identifier, basic, usage, force, moment, consumers in webpier["auxiliary_actions"]:
        row = native["load"][str(identifier)]["load_node"][0]
        assert (row["ty"], row["rz"]) == (-force, -moment)
        assert native["load"][str(identifier)]["fix_node"] == 2
        assert native["define"][str(identifier)] == {"row": identifier, "C1": identifier}
        mapping = next(row for row in exported.source_mapping["auxiliary_cases"] if row["native_load_id"] == identifier)
        assert mapping["basic_case_id"] == basic and mapping["usage"] == usage
        assert mapping["combination_ids"] == consumers
        for consumer in consumers:
            assert native["combine"][str(consumer)][f"C{identifier}"] == 1
    for identifier in range(1, 21):
        assert native["define"][str(identifier)] == example["define"][str(identifier)]
    for identifier, row in native["pickup"].items():
        assert {key: value for key, value in row.items() if key != "name"} == {
            key: value for key, value in example["pickup"][identifier].items() if key != "name"}
    assert exported.source_mapping["verified_variant_count"] == 28
    assert_all_vectors(current_result, native)
    assert len(webpier["reference_states"]) == 28
    for state in webpier["reference_states"]:
        expected = {tuple(row[:-1]): row[-1] for row in state["actions"]}
        assert native_vector(native, state["combination_id"], state["horizontal_sign"]) == expected


@pytest.mark.parametrize("rho,service", [(0, 1), (1.23, 0), (1.231, 0.83), (1.23, 1.37)])
def test_zero_and_nonstandard_factors_keep_all_meanings_and_vectors(rho, service):
    source = canonical_input(rho=rho, service=service)
    exported = build_frameweb_input(source)
    native = exported.document
    assert set(native["load"]) == {str(identifier) for identifier in range(1, 29)}
    assert [row["native_load_id"] for row in exported.source_mapping["auxiliary_cases"]] == list(range(21, 29))
    assert_all_vectors(source, native)
    if rho == 0:
        assert {11, 12, 23, 24, 27, 28} <= set(exported.source_mapping["zero_load_case_ids"])
    if service == 0:
        assert {21, 22, 25, 26} <= set(exported.source_mapping["zero_load_case_ids"])


@pytest.mark.parametrize("change", ["aux_collision", "effective_factor", "resolved_nominal", "variant_vertical_sign", "variant_missing", "unused_impact", "pickup_group", "variant_nominal"])
def test_reject_incompatible_cases_and_resolved_vectors(current_result, change):
    source = deepcopy(current_result)
    if change == "aux_collision":
        source["combinations"][9]["resolved_components"][9]["loads"]["M"] += 0.01
    elif change == "effective_factor":
        source["combinations"][0]["resolved_components"][11]["resolution"]["effective_train_factor"] = 1.35 * 1.35
    elif change == "resolved_nominal":
        source["combinations"][0]["resolved_components"][0]["nominal_factor"] = 1.2
    elif change == "variant_vertical_sign":
        source["combinations"][0]["variants"][1]["resolved_components"][0]["loads"]["top"]["N"] *= -1
    elif change == "variant_missing":
        source["combinations"][0]["variants"].pop()
    elif change == "unused_impact":
        source["combinations"][1]["coefficients"][11] = 1.23
        source["combinations"][1]["resolved_components"][11].update(nominal_factor=1.23, residual_factor=1)
        source["combinations"][1]["resolved_components"][11]["resolution"]["included"] = True
    elif change == "pickup_group":
        source["extraction_cases"][0]["combination_ids"], source["extraction_cases"][5]["combination_ids"] = (
            source["extraction_cases"][5]["combination_ids"], source["extraction_cases"][0]["combination_ids"])
    else:
        source["combinations"][0]["variants"][1]["resolved_components"][0]["nominal_factor"] = 9
    with pytest.raises(InputError):
        build_frameweb_input(source)


def test_zero_service_retains_available_zero_variable_response():
    source = canonical_input(service=0)
    exported = build_frameweb_input(source)
    native, mapping = exported.document, exported.source_mapping
    assert native["combine"]["7"] == {"row": 7, "name": source["combinations"][6]["label"], "C21": 1, "C25": 1}
    for combination, columns in ((5, (22, 26)), (7, (21, 25)), (15, (21, 25)), (16, (21, 25))):
        for column in columns:
            assert native["combine"][str(combination)][f"C{column}"] == 1
    assert native["load"]["21"]["load_node"] == [
        {"n": str(source["frame"]["load_anchors"]["cap_top"]["node_id"]), "tx": 0, "ty": 0,
         "tz": None, "rx": None, "ry": None, "rz": 0, "row": 1}]
    assert "load_node" not in native["load"]["5"]
    assert mapping["zero_load_case_ids"] == [5, 21, 22, 25, 26]
    assert mapping["skipped_load_case_ids"] == [5, 22, 25, 26]
    assert mapping["retained_zero_response_case_ids"] == [21]
    reference = next(row for row in mapping["combinations"] if row["id"] == 7)["components"][8]
    assert reference["nominal_factor"] == 0 and reference["native_factor"] == 1
    validate_frameweb_input(json.loads(json.dumps(native)))
    assert_all_vectors(source, native)
    # Model the runner's availability boundary separately from force vectors:
    # empty saved cases are skipped, an explicit zero node row yields a result.
    available = {int(key) for key, case in native["load"].items() if case.get("load_node") or case.get("load_member")}
    assert len(available) == 24
    for combination in native["combine"].values():
        references = [native["define"][key[1:]]["C1"] for key in combination if key.startswith("C")]
        assert any(abs(reference) in available for reference in references)


@pytest.mark.parametrize("target", ["basic", "wrong_aux", "unnecessary", "missing", "missing_reference"])
def test_zero_row_exception_is_limited_to_required_zero_variable_case(target, current_result):
    source = canonical_input(service=0) if target in ("missing", "missing_reference") else current_result
    native = build_frameweb_input(source).document
    zero = {"n": "1", "tx": 0, "ty": 0, "tz": None, "rx": None, "ry": None, "rz": 0, "row": 1}
    if target == "missing":
        native["load"]["21"].pop("load_node", None)
    elif target == "missing_reference":
        native["combine"]["7"].pop("C21", None)
    else:
        identifier = {"basic": "5", "wrong_aux": "22", "unnecessary": "21"}[target]
        native["load"][identifier]["load_node"] = [zero]
    with pytest.raises(InputError):
        validate_frameweb_input(native)


@pytest.mark.parametrize("force", [1e-11, 1])
@pytest.mark.parametrize("target", ["base", "variant"])
def test_nominal_zero_cannot_hide_nonzero_resolved_action(force, target):
    source = canonical_input(service=0)
    if target == "base":
        for identifier in (7, 15, 16):
            combination = source["combinations"][identifier - 1]
            combination["resolved_components"][8]["loads"]["N"] = force
            for variant in combination["variants"]:
                variant["resolved_components"][8]["loads"]["N"] = force
    else:
        source["combinations"][6]["variants"][0]["resolved_components"][8]["loads"]["N"] = force
    with pytest.raises(InputError, match="excluded_components"):
        build_frameweb_input(source)
