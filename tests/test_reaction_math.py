"""0600 Excel precision normalization before ROUND."""

import importlib
import json
from decimal import getcontext, localcontext
from pathlib import Path

import pytest

from src.inputs import InputError


ORACLE = json.loads((Path(__file__).parent / "fixtures" / "reaction_round_oracle.json").read_text(encoding="utf-8"))


def excel_round(value, places=0):
    return importlib.import_module("src.reaction_math").excel_round(value, places)


@pytest.mark.parametrize(("value", "places", "expected"), [
    (639.9749999999999, 2, 639.98),  # Independent Excel distribution_slots!AC22
    (-639.9749999999999, 2, -639.98),
    (0.5, 0, 1), (-0.5, 0, -1),
    (1.2345, 3, 1.235), (-1.2345, 3, -1.235),
    (123.45, -1, 120), (15, -1, 20),
    (1.2344999999999, 3, 1.234),
])
def test_round_matches_excel(value, places, expected):
    assert excel_round(value, places) == expected


@pytest.mark.parametrize(("value", "places", "expected"), [
    (case["input"], item["places"], item["excel"])
    for case in ORACLE["cases"] for item in case["places"]
])
def test_independent_excel_boundary_oracle(value, places, expected):
    assert excel_round(value, places) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 1e100, True, "1.5"])
def test_invalid_or_excessive_values_are_input_errors(value):
    with pytest.raises(InputError):
        excel_round(value, 2)


@pytest.mark.parametrize(("value", "expected"), [(1e30, 1e30), (-1e30, -1e30)])
def test_round_accepts_large_values_within_single_range(value, expected):
    assert excel_round(value, 2) == expected


@pytest.mark.parametrize("value", [1.2345, 1e30, -1e30])
def test_round_success_preserves_callers_decimal_context(value):
    with localcontext() as context:
        context.clear_flags()
        snapshot = str(context)
        excel_round(value, 2)
        assert getcontext() is context
        assert str(context) == snapshot


@pytest.mark.parametrize("value", [1e100, float("inf")])
def test_round_failure_preserves_callers_decimal_context(value):
    with localcontext() as context:
        context.clear_flags()
        snapshot = str(context)
        with pytest.raises(InputError):
            excel_round(value, 2)
        assert getcontext() is context
        assert str(context) == snapshot
