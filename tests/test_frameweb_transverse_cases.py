"""Independent candidate enumeration: no production case-expansion helpers."""

from copy import deepcopy
from itertools import product
import json
import re

import pytest

from src.inputs import InputError
from src.frameweb_export import build_frameweb_input, validate_frameweb_input
from test_frameweb_transverse_export import canonical_input, current_result, FIXTURES


def physical_vector(loads, spring):
    vector = {}
    for point in loads["points"]:
        for axis, value in (("tx", point["H"]), ("ty", -point["N"]), ("rz", -point["M"])):
            key = spring, "node", point["node_id"], axis
            vector[key] = vector.get(key, 0) + value
    for line in loads["line_loads"]:
        for member in line["member_ids"]:
            for axis, value in (("gx", line["qH"]), ("gy", -line["qN"])):
                key = spring, "member", member, axis
                vector[key] = vector.get(key, 0) + value
    return vector


def saved_vector(case):
    result = {}
    for row in case.get("load_node", []):
        for axis in ("tx", "ty", "rz"):
            key = case["fix_node"], "node", int(row["n"]), axis
            result[key] = result.get(key, 0) + (row[axis] or 0)
    for row in case.get("load_member", []):
        key = case["fix_node"], "member", int(row["m1"]), row["direction"]
        result[key] = result.get(key, 0) + row["P1"]
    return result


def add_vectors(*vectors):
    result = {}
    for vector in vectors:
        for key, value in vector.items():
            result[key] = result.get(key, 0) + value
    return result


def assert_states(source, native):
    counts = []
    for combination in source["combinations"]:
        expected = []
        for chosen in product(*(c["candidates"] for c in combination["resolved_components"])):
            tracks = {c["direction"] for c in chosen if c.get("compatibility_group") == "single_track"}
            if len(tracks) > 1:
                continue
            expected.append(add_vectors(*(physical_vector(c["loads"], source["basic_cases"][c["basic_case_id"] - 1]["spring_case"])
                                          for c in chosen)))
        options = []
        for key, factor in native["combine"][str(combination["id"])].items():
            if not key.startswith("C"):
                continue
            choices = []
            for column, signed in native["define"][key[1:]].items():
                if column.startswith("C"):
                    vector = saved_vector(native["load"][str(abs(signed))])
                    choices.append({k: value * factor * (1 if signed > 0 else -1) for k, value in vector.items()})
            options.append(choices)
        actual = [add_vectors(*choices) for choices in product(*options)]
        assert len(actual) == len(expected)
        keys = sorted(set().union(*(v.keys() for v in [*actual, *expected])))
        # Sort full physical vectors, never combine independently selected extrema.
        actual_rows = sorted(tuple(v.get(key, 0) for key in keys) for v in actual)
        expected_rows = sorted(tuple(v.get(key, 0) for key in keys) for v in expected)
        for a, e in zip(actual_rows, expected_rows, strict=True):
            assert a == pytest.approx(e, rel=1e-12, abs=1e-10)
        counts.append(len(expected))
    return counts


def test_all_240_nominal_coefficients_defines_pickups_and_37_states(current_result):
    reference = json.loads((FIXTURES / "frameweb_transverse_example2_mapping.json").read_text(encoding="utf-8"))
    exported = build_frameweb_input(current_result)
    native = exported.document
    assert [row["coefficients"] for row in current_result["combinations"]] == reference["coefficients"]
    assert [[row[f"C{i}"] for i in range(1, len(row))] for row in list(native["define"].values())[:15]] == reference["define"]
    for row, expected in zip(native["pickup"].values(), reference["pickup"], strict=True):
        assert [value for key, value in row.items() if key.startswith("C")] == expected
    assert assert_states(current_result, native) == [4,4,2,1,1,1,2,4,2,4,4,2,1,1,2,2]
    for combination in exported.source_mapping["combinations"]:
        assert len(combination["components"]) == 15
        assert [row["nominal_factor"] for row in combination["components"]] == reference["coefficients"][combination["id"] - 1]
    assert native["combine"]["9"]["C14"] == 1  # Snow recovery intentionally uses W1.
    for combine in native["combine"].values():
        assert not {"C9", "C10", "C11", "C12"} & combine.keys()


@pytest.mark.parametrize("rho,service", [(1.111, .83), (1.23, 1), (0, 1)])
def test_custom_and_zero_factors_retain_fixed_semantic_slots(rho, service):
    source = canonical_input(rho=rho, service=service)
    exported = build_frameweb_input(source)
    native = exported.document
    assert list(native["load"]) == [str(i) for i in range(1, 23)]
    assert list(native["define"]) == [str(i) for i in range(1, 20)]
    assert sum(assert_states(source, native)) == exported.source_mapping["verified_variant_count"]
    if not rho:
        assert all(not native["load"][str(i)].get("load_node") for i in (18, 19))
        assert "C16" not in native["combine"]["1"]


@pytest.mark.parametrize("rho", [1.231, 0])
def test_zero_service_is_rejected_before_publishing_unavailable_pickup_reference(rho):
    # The specified headless excludes zero-term COMBINE7, so PICKUP4 would
    # reference an unavailable combination. Do not fabricate a nonzero load.
    source = canonical_input(rho=rho, service=0)
    assert source["combinations"][6]["resolved_components"] == []
    with pytest.raises(InputError, match=r"combine\.7.*全ゼロ.*PICKUP"):
        build_frameweb_input(source)


def test_native_reload_rejects_empty_combination_used_by_pickup(current_result):
    native = build_frameweb_input(current_result).document
    native["combine"]["7"] = {"row": 7, "name": "zero"}
    with pytest.raises(InputError, match=r"combine\.7.*全ゼロ.*PICKUP"):
        validate_frameweb_input(native, stage="0620")


def test_native_reload_propagates_skipped_zero_loads_to_pickup_availability(current_result):
    native = build_frameweb_input(current_result).document
    # A nonzero coefficient referencing exclusively skipped zero cases is
    # unavailable too. Conversely the existing WP3 zero case is harmless in
    # combinations which contain other real actions.
    assert native["combine"]["7"]["C19"] == 1
    for identifier in ("21", "22"):
        native["load"][identifier].pop("load_node")
    with pytest.raises(InputError, match=r"combine\.7.*全ゼロ.*PICKUP"):
        validate_frameweb_input(native, stage="0620")


def test_partial_zero_track_candidate_cannot_disappear_from_envelope(current_result):
    native = build_frameweb_input(current_result).document
    native["load"]["21"].pop("load_node")
    with pytest.raises(InputError, match=r"define\.19.*ゼロ候補.*包絡"):
        validate_frameweb_input(native, stage="0620")


@pytest.mark.parametrize("epsilon", [0, .00001, .00042, .00051, .001])
def test_signed_asymmetric_rates_keep_zero_force_couples_and_track_choice(epsilon):
    source = canonical_input(epsilon=epsilon)
    native = build_frameweb_input(source).document
    assert_states(source, native)
    up, down = native["load"]["21"]["load_node"][0], native["load"]["22"]["load_node"][0]
    assert up["ty"] != down["ty"]
    assert up["rz"] != 0
    if epsilon == 0:
        assert up["ty"] is None  # A pure couple remains a real load case.


def test_independent_track_selection_is_detected_even_when_symmetric_extrema_match(current_result):
    source = deepcopy(current_result)
    for combination in source["combinations"]:
        for component in combination["resolved_components"]:
            if component["define_case_id"] == 11:
                for candidate in component["candidates"]:
                    candidate["loads"]["points"][0]["M"] *= -1
    native = build_frameweb_input(source).document
    assert_states(source, native)
    assert abs(native["load"]["21"]["load_node"][0]["rz"]) == pytest.approx(1210.08 - 272.73)
    invalid = deepcopy(native)
    invalid["combine"]["7"] = {"row": 7, "name": "uncoupled", "C9": 1, "C11": .75}
    with pytest.raises(AssertionError):
        assert_states(source, invalid)


@pytest.mark.parametrize("path,value", [
    (("direction",), "longitudinal"), (("schema_version",), 1), (("case_model_version",), "future"),
    (("units", "force"), "N"), (("basic_cases", 8, "spring_case"), 1),
    (("define_cases", 8, "selection_group"), "unknown"),
    (("frame", "spring_provenance", "direction"), "longitudinal"),
    (("frame", "springs", "long_term", "Kr"), 1),
    (("frame", "load_anchors", "column_line_load", "member_ids"), [1, 2, 4]),
    (("combinations", 6, "resolved_components", 1, "candidates", 0, "compatibility_group"), "unknown"),
    (("combinations", 6, "resolved_components", 1, "candidates", 0, "direction"), "down"),
    (("combinations", 6, "resolved_components", 1, "candidates", 0, "coefficient_trace", "remaining_multiplier"), .75),
    (("combinations", 6, "resolved_components", 1, "candidates", 0, "coefficient_trace", "effective_factor"), .75),
])
def test_reject_unknown_version_group_spring_and_coefficient_contract(current_result, path, value):
    source = deepcopy(current_result)
    target = source
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(InputError):
        build_frameweb_input(source)


def test_reject_missing_impact_or_conflicting_shared_helper(current_result):
    missing = deepcopy(current_result)
    missing["combinations"][6]["resolved_components"].pop()
    conflict = deepcopy(current_result)
    conflict["combinations"][14]["resolved_components"][-1]["candidates"][0]["loads"]["points"][0]["M"] += 1
    for source in (missing, conflict):
        with pytest.raises(InputError):
            build_frameweb_input(source)


@pytest.mark.parametrize("change", ["bool_basic_id", "float_signed_id", "extra_action", "bool_component_id"])
def test_canonical_ids_have_exact_types_and_all_registered_actions_are_known(current_result, change):
    source = deepcopy(current_result)
    first = source["combinations"][0]["resolved_components"][0]
    if change == "bool_basic_id":
        first["candidates"][0]["basic_case_id"] = True
    elif change == "float_signed_id":
        first["candidates"][0]["signed_basic_case_id"] = 1.0
    elif change == "bool_component_id":
        first["define_case_id"] = True
    else:
        source["actions"]["unknown"] = deepcopy(source["actions"]["dead_fixed"])
    with pytest.raises(InputError):
        build_frameweb_input(source)


def test_input_rho_precision_is_preserved_before_impact_resolution(current_result):
    rounded_input = canonical_input(rho=1.23)
    assert current_result["factor_parameters"]["ultimate_factor"] == 1.231
    assert current_result["combinations"][0]["coefficients"] == rounded_input["combinations"][0]["coefficients"]
    current_native = build_frameweb_input(current_result).document
    rounded_native = build_frameweb_input(rounded_input).document
    assert current_native["load"]["14"]["load_node"][0]["ty"] == -328.7
    assert rounded_native["load"]["14"]["load_node"][0]["ty"] == -328.6


def test_helper_source_paths_resolve_to_the_recorded_canonical_candidates(current_result):
    mapping = build_frameweb_input(current_result).source_mapping
    for helper in mapping["auxiliary_cases"]:
        assert helper["sources"]
        for source in helper["sources"]:
            assert "=" not in source["source_path"]
            value = current_result
            for token in re.findall(r"[A-Za-z_]+|\d+", source["source_path"]):
                value = value[int(token)] if token.isdigit() else value[token]
            assert value["basic_case_id"] == source["basic_case_id"]
            assert value["coefficient_trace"] == source["coefficient_trace"]
