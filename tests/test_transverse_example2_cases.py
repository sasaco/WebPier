"""Canonical transverse cases against the independent Example2 PDF fixture."""

import builtins
from copy import deepcopy
import importlib
import io
import json
from pathlib import Path

import pytest

from src.inputs import InputError


REFERENCE = Path(__file__).parent / "fixtures" / "transverse_example2_cases.json"


def cases_module():
    return importlib.import_module("src.transverse_example2_cases")


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def test_standard_model_matches_all_independent_pdf_definitions(reference):
    module = cases_module()
    model = module.build_case_model(ultimate_factor=1.23, service_factor=1.0)
    assert model["case_model_version"] == "example2-nonseismic-pier-impact-v1"
    assert model["coefficient_define_case_ids"] == list(range(1, 16))
    for collection in ("basic_cases", "define_cases", "combinations", "extraction_cases"):
        expected_rows = reference[collection]
        assert len(model[collection]) == len(expected_rows)
        for actual, expected in zip(model[collection], expected_rows, strict=True):
            assert {key: actual[key] for key in expected} == expected
    for index, combination in enumerate(model["combinations"]):
        assert combination["coefficients"] == [row[index] for row in reference["coefficient_matrix"]["values"]]
        assert combination["usage"] == ("service" if index + 1 in {5, 6, 7, 14, 15, 16} else "ultimate")
    assert sum(len(case["coefficients"]) for case in model["combinations"]) == 240
    before = deepcopy(model)
    module.validate_case_model(model)
    assert model == before


@pytest.mark.parametrize("ultimate,service,ordinary,maximum,service_impact", [
    (1.231, 1.0, 1.23, 1.35, 0.75),
    (1.235, 1.0, 1.24, 1.36, 0.75),
    (0.0, 1.0, 0.0, 0.0, 0.75),
    (1.23, 1.2, 1.23, 1.35, 0.9),
    (1.23, 0.0, 1.23, 1.35, 0.0),
])
def test_adopted_factor_variants_preserve_definitions_and_zero_cells(
    ultimate, service, ordinary, maximum, service_impact, reference,
):
    module = cases_module()
    model = module.build_case_model(ultimate_factor=ultimate, service_factor=service)
    rows = list(map(list, zip(*(case["coefficients"] for case in model["combinations"]), strict=True)))
    assert rows[8] == [0, 0, 0, 0, 0, 0, service, 0, 0, 0, 0, 0, 0, 0, service, service]
    assert rows[9] == [maximum, ordinary, 0, 0, service, 0, 0, ordinary, 0, maximum, ordinary, 0, 0, 0, 0, 0]
    assert rows[10] == pytest.approx([0, 0, 0, 0, 0, 0, service_impact, 0, 0, 0, 0, 0, 0, 0,
                                    service_impact, service_impact], rel=0, abs=1e-12)
    assert rows[11] == pytest.approx([maximum, ordinary, 0, 0, service_impact, 0, 0, ordinary, 0,
                                    maximum, ordinary, 0, 0, 0, 0, 0], rel=0, abs=1e-12)
    assert rows[12] == [ordinary, maximum, 0, 0, 0, 0, 0, ordinary, 0, ordinary, maximum, 0, 0, 0, 0, 0]
    for index in (*range(8), 13, 14):
        assert rows[index] == reference["coefficient_matrix"]["values"][index]
    assert model["factor_parameters"] == {
        "ultimate_factor": ultimate, "service_factor": service,
        "ordinary_factor": ordinary, "maximum_factor": maximum,
    }
    module.validate_case_model(model)


def test_models_do_not_share_mutable_rows_or_coefficients():
    module = cases_module()
    first = module.build_case_model(ultimate_factor=1.23, service_factor=1)
    second = module.build_case_model(ultimate_factor=1.23, service_factor=1)
    original = deepcopy(second)
    first["define_cases"][8]["signed_basic_case_ids"][0] = 999
    first["define_cases"][8]["option_keys"][0] = "changed"
    first["combinations"][0]["coefficients"][0] = 999
    first["extraction_cases"][0]["combination_ids"][0] = 999
    assert second == original
    assert module.build_case_model(ultimate_factor=1.23, service_factor=1) == original


@pytest.mark.parametrize("parameter", ["ultimate_factor", "service_factor"])
@pytest.mark.parametrize("bad", [None, True, False, "1.23", [], {}, -0.01, float("nan"), float("inf"), 10 ** 400])
def test_invalid_factors_raise_named_input_errors(parameter, bad):
    arguments = {"ultimate_factor": 1.23, "service_factor": 1.0}
    arguments[parameter] = bad
    with pytest.raises(InputError, match=parameter):
        cases_module().build_case_model(**arguments)


@pytest.mark.parametrize("corruption,expected_path", [
    ("duplicate_basic_id", "basic_cases"),
    ("boolean_basic_id", "basic_cases"),
    ("unknown_basic_id", "basic_cases"),
    ("duplicate_basic_key", "basic_cases"),
    ("wrong_basic_track", "basic_cases"),
    ("wrong_basic_spring", "basic_cases"),
    ("missing_basic", "basic_cases"),
    ("non_object_basic", "basic_cases"),
    ("duplicate_define_id", "define_cases"),
    ("unknown_define_basic", "define_cases"),
    ("boolean_define_basic", "define_cases"),
    ("vertical_negative_define", "define_cases"),
    ("mixed_single_track_order", "define_cases"),
    ("uncoupled_single_track_group", "define_cases"),
    ("wrong_single_track_options", "define_cases"),
    ("summed_single_track", "define_cases"),
    ("wrong_horizontal_sign_scope", "define_cases"),
    ("missing_horizontal_negative", "define_cases"),
    ("overwritten_source_alias", "define_cases"),
    ("duplicate_combination_id", "combinations"),
    ("unknown_combination_id", "combinations"),
    ("wrong_combination_usage", "combinations"),
    ("wrong_combination_scope", "combinations"),
    ("missing_coefficient", "coefficients"),
    ("negative_coefficient", "coefficients"),
    ("nan_coefficient", "coefficients"),
    ("boolean_coefficient", "coefficients"),
    ("wrong_finite_coefficient", "coefficients"),
    ("reordered_coefficient_axis", "coefficient_define_case_ids"),
    ("unknown_extraction_combination", "extraction_cases"),
    ("missing_extraction_member", "extraction_cases"),
    ("duplicate_extraction_id", "extraction_cases"),
    ("wrong_factor_trace", "factor_parameters"),
    ("unknown_model_version", "case_model_version"),
])
def test_validator_rejects_inconsistent_references_and_coefficients(corruption, expected_path):
    module = cases_module()
    model = module.build_case_model(ultimate_factor=1.23, service_factor=1)
    if corruption == "duplicate_basic_id":
        model["basic_cases"][1]["id"] = 1
    elif corruption == "boolean_basic_id":
        model["basic_cases"][0]["id"] = True
    elif corruption == "unknown_basic_id":
        model["basic_cases"][0]["id"] = 99
    elif corruption == "duplicate_basic_key":
        model["basic_cases"][1]["key"] = "dead_fixed"
    elif corruption == "wrong_basic_track":
        model["basic_cases"][8]["track"] = "down"
    elif corruption == "wrong_basic_spring":
        model["basic_cases"][14]["spring_case"] = 1
    elif corruption == "missing_basic":
        model["basic_cases"].pop()
    elif corruption == "non_object_basic":
        model["basic_cases"][0] = None
    elif corruption == "duplicate_define_id":
        model["define_cases"][1]["id"] = 1
    elif corruption == "unknown_define_basic":
        model["define_cases"][0]["signed_basic_case_ids"] = [99]
    elif corruption == "boolean_define_basic":
        model["define_cases"][0]["signed_basic_case_ids"] = [True]
    elif corruption == "vertical_negative_define":
        model["define_cases"][0].update(signed_basic_case_ids=[1, -1], selection_kind="horizontal_sign")
    elif corruption == "mixed_single_track_order":
        model["define_cases"][10]["signed_basic_case_ids"] = [13, 12]
    elif corruption == "uncoupled_single_track_group":
        model["define_cases"][10]["selection_group"] = "independent_impact"
    elif corruption == "wrong_single_track_options":
        model["define_cases"][10]["option_keys"] = ["down", "up"]
    elif corruption == "summed_single_track":
        model["define_cases"][8]["selection_kind"] = "sum"
    elif corruption == "wrong_horizontal_sign_scope":
        model["define_cases"][12]["sign_scope"] = "all_actions"
    elif corruption == "missing_horizontal_negative":
        model["define_cases"][12]["signed_basic_case_ids"] = [15]
    elif corruption == "overwritten_source_alias":
        model["define_cases"][9]["source_symbol"] = "L2"
    elif corruption == "duplicate_combination_id":
        model["combinations"][1]["id"] = 1
    elif corruption == "unknown_combination_id":
        model["combinations"][0]["id"] = 99
    elif corruption == "wrong_combination_usage":
        model["combinations"][4]["usage"] = "ultimate"
    elif corruption == "wrong_combination_scope":
        model["combinations"][9]["scope"] = "body"
    elif corruption == "missing_coefficient":
        model["combinations"][0]["coefficients"].pop()
    elif corruption == "negative_coefficient":
        model["combinations"][0]["coefficients"][0] = -1
    elif corruption == "nan_coefficient":
        model["combinations"][0]["coefficients"][0] = float("nan")
    elif corruption == "boolean_coefficient":
        model["combinations"][0]["coefficients"][6] = True
    elif corruption == "wrong_finite_coefficient":
        model["combinations"][8]["coefficients"][13] = 0
    elif corruption == "reordered_coefficient_axis":
        model["coefficient_define_case_ids"][0:2] = [2, 1]
    elif corruption == "unknown_extraction_combination":
        model["extraction_cases"][0]["combination_ids"][0] = 99
    elif corruption == "missing_extraction_member":
        model["extraction_cases"][0]["combination_ids"].pop()
    elif corruption == "duplicate_extraction_id":
        model["extraction_cases"][1]["id"] = 1
    elif corruption == "wrong_factor_trace":
        model["factor_parameters"]["maximum_factor"] = 1.353
    elif corruption == "unknown_model_version":
        model["case_model_version"] = "legacy"
    else:
        raise AssertionError(corruption)
    with pytest.raises(InputError, match=expected_path):
        module.validate_case_model(model)


def test_validator_preserves_attached_action_data_without_evaluating_it():
    module = cases_module()
    model = module.build_case_model(ultimate_factor=1.23, service_factor=1)
    model["basic_cases"][0]["loads"] = {"points": [{"N": 12, "H": 0, "M": -3}]}
    model["combinations"][0]["resolved_components"] = [{"resolved_by": "actions"}]
    before = deepcopy(model)
    module.validate_case_model(model)
    assert model == before


def test_case_module_does_not_read_the_fixture_or_pdf_at_runtime(monkeypatch):
    def guard(original_open):
        def checked(file, *args, **kwargs):
            if not isinstance(file, int):
                path = Path(file)
                if "fixtures" in path.parts or path.suffix.lower() in {".json", ".pdf", ".xls", ".xlsx"}:
                    pytest.fail(f"Case model read reference data at runtime: {path}")
            return original_open(file, *args, **kwargs)
        return checked

    with monkeypatch.context() as protected:
        protected.setattr(builtins, "open", guard(builtins.open))
        protected.setattr(io, "open", guard(io.open))
        module = importlib.reload(cases_module())
        model = module.build_case_model(ultimate_factor=1.23, service_factor=1)
        module.validate_case_model(model)
    assert len(model["combinations"]) == 16
