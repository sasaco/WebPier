"""0610 canonical case definitions against the independent Example2 fixture."""

import builtins
from copy import deepcopy
import importlib
import io
import json
from pathlib import Path

import pytest

from src.inputs import InputError


REFERENCE = Path(__file__).parent / "fixtures" / "longitudinal_example2_cases.json"


def cases_module():
    # An unimplemented API fails a running test rather than test collection.
    return importlib.import_module("src.longitudinal_example2_cases")


@pytest.fixture(scope="module")
def reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def test_standard_case_model_matches_all_independent_pdf_definitions(reference):
    module = cases_module()
    model = module.build_case_model(ultimate_factor=1.23, service_factor=1.0)
    assert model["case_model_version"] == "example2-nonseismic-pier-impact-v1"
    assert len(model["basic_cases"]) == 20
    for actual, expected in zip(model["basic_cases"], reference["basic_cases"], strict=True):
        observed = {key: actual[key] for key in expected}
        observed["label"] = actual["source_label"]
        observed["symbol"] = actual.get("source_symbol", actual["symbol"])
        assert observed == expected
        if actual["id"] == 19:
            assert "側別" in actual["label"]
            assert "1.23" not in actual["label"]
            assert "1.23" not in actual["symbol"]

    assert len(model["combinations"]) == 16
    for column, (actual, expected) in enumerate(zip(model["combinations"], reference["combinations"], strict=True)):
        assert {key: actual[key] for key in expected} == expected
        assert actual["coefficients"] == [row[column] for row in reference["coefficient_matrix"]["values"]]
    assert sum(len(case["coefficients"]) for case in model["combinations"]) == 320

    assert len(model["define_cases"]) == 20
    for actual, expected in zip(model["define_cases"], reference["define_cases"], strict=True):
        observed = {key: actual[key] for key in expected}
        observed["symbol"] = actual.get("source_symbol", actual["symbol"])
        assert observed == expected
        if actual["id"] == 19:
            assert "1.23" not in actual["symbol"]
    assert len(model["extraction_cases"]) == 8
    for actual, expected in zip(model["extraction_cases"], reference["extraction_cases"], strict=True):
        assert {key: actual[key] for key in expected} == expected
    original = deepcopy(model)
    module.validate_case_model(model)
    assert model == original


@pytest.mark.parametrize("ultimate,service,ordinary,maximum,service_impact", [
    (1.231, 1.0, 1.23, 1.35, 0.75),
    (1.235, 1.0, 1.24, 1.36, 0.75),
    (0.0, 1.0, 0.0, 0.0, 0.75),
    (1.23, 1.2, 1.23, 1.35, 0.9),
    (1.23, 0.0, 1.23, 1.35, 0.0),
])
def test_factor_variants_keep_effective_rounding_service_nominals_and_zero_cells(
    ultimate, service, ordinary, maximum, service_impact, reference,
):
    model = cases_module().build_case_model(ultimate_factor=ultimate, service_factor=service)
    by_basic = list(map(list, zip(*(case["coefficients"] for case in model["combinations"]), strict=True)))
    assert by_basic[8] == [0, 0, 0, 0, 0, 0, service, 0, 0, 0, 0, 0, 0, 0, service, service]
    assert by_basic[9] == [maximum, ordinary, ordinary, 0, service, 0, 0, ordinary, 0,
                           maximum, ordinary, ordinary, 0, 0, 0, 0]
    assert by_basic[10] == pytest.approx(
        [0, 0, 0, 0, 0, 0, service_impact, 0, 0, 0, 0, 0, 0, 0, service_impact, service_impact],
        rel=0, abs=1e-12,
    )
    assert by_basic[11] == pytest.approx(
        [maximum, 0, ordinary, 0, service_impact, 0, 0, ordinary, 0, maximum, 0, ordinary, 0, 0, 0, 0],
        rel=0, abs=1e-12,
    )
    # Only the nonzero service product needs binary-float tolerance. The
    # source's excluded impact cells must still be exactly zero.
    for index in (10, 11):
        for column, source_coefficient in enumerate(reference["coefficient_matrix"]["values"][index]):
            if source_coefficient == 0:
                assert by_basic[index][column] == 0
    for index in (*range(8), *range(12, 20)):
        assert by_basic[index] == reference["coefficient_matrix"]["values"][index]
    cases_module().validate_case_model(model)


@pytest.mark.parametrize("parameter", ["ultimate_factor", "service_factor"])
@pytest.mark.parametrize("bad", [None, True, False, "1.23", -0.01, float("nan"), float("inf")])
def test_invalid_factor_is_an_input_error(parameter, bad):
    arguments = {"ultimate_factor": 1.23, "service_factor": 1.0}
    arguments[parameter] = bad
    with pytest.raises(InputError, match=parameter):
        cases_module().build_case_model(**arguments)


@pytest.mark.parametrize("corruption,expected_path", [
    ("duplicate_basic_id", "basic_cases"),
    ("unknown_basic_id", "basic_cases"),
    ("duplicate_basic_key", "basic_cases"),
    ("duplicate_combination_id", "combinations"),
    ("unknown_combination_id", "combinations"),
    ("missing_coefficient", "coefficients"),
    ("vertical_negative_define", "define_cases"),
    ("unknown_define_basic", "define_cases"),
    ("unknown_extraction_combination", "extraction_cases"),
])
def test_validator_rejects_malformed_case_references(corruption, expected_path):
    module = cases_module()
    model = module.build_case_model(ultimate_factor=1.23, service_factor=1)
    if corruption == "duplicate_basic_id":
        model["basic_cases"][1]["id"] = 1
    elif corruption == "unknown_basic_id":
        model["basic_cases"][0]["id"] = 99
    elif corruption == "duplicate_basic_key":
        model["basic_cases"][1]["key"] = model["basic_cases"][0]["key"]
    elif corruption == "duplicate_combination_id":
        model["combinations"][1]["id"] = 1
    elif corruption == "unknown_combination_id":
        model["combinations"][0]["id"] = 99
    elif corruption == "missing_coefficient":
        model["combinations"][0]["coefficients"].pop()
    elif corruption == "vertical_negative_define":
        model["define_cases"][0]["signed_basic_case_ids"] = [1, -1]
        model["define_cases"][0]["sign_scope"] = "horizontal_action_only"
    elif corruption == "unknown_define_basic":
        model["define_cases"][0]["basic_case_id"] = 99
        model["define_cases"][0]["signed_basic_case_ids"] = [99]
    elif corruption == "unknown_extraction_combination":
        model["extraction_cases"][0]["combination_ids"] = [99, 2, 3, 4]
    with pytest.raises(InputError, match=expected_path):
        module.validate_case_model(model)


def test_production_case_model_never_reads_reference_documents_or_fixtures(monkeypatch):
    def guard(original_open):
        def checked(file, *args, **kwargs):
            if not isinstance(file, int):
                path = Path(file)
                if "fixtures" in path.parts or path.suffix.lower() in {".json", ".pdf", ".xls", ".xlsx"}:
                    pytest.fail(f"Production case definitions must not load reference files: {path}")
            return original_open(file, *args, **kwargs)
        return checked

    # Restrict the guard to this product module's import and API calls; normal
    # Python module/bytecode reads are allowed even within that interval.
    with monkeypatch.context() as protected:
        protected.setattr(builtins, "open", guard(builtins.open))
        protected.setattr(io, "open", guard(io.open))
        # Reload also catches fixture reads performed at module import time.
        module = importlib.reload(cases_module())
        model = module.build_case_model(ultimate_factor=1.23, service_factor=1)
        module.validate_case_model(model)
    assert len(model["basic_cases"]) == 20
    assert len(model["combinations"]) == 16
