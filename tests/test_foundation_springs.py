"""Directional handoff from 0500 normal results, without Single macro values."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import re

import pytest

from src.calculator import calculate
from src.inputs import InputError, parse_input


BASELINE = Path(__file__).parent / "fixtures" / "baseline_input.json"


def spring_set(foundation, direction):
    # Called by tests, so an unimplemented module fails a test, not collection.
    module = importlib.import_module("src.foundation_springs")
    return module.foundation_spring_set(foundation, direction)


@pytest.fixture
def synthetic_foundation():
    return {
        "long_term": {"Kv": 16777217, "Ks": 16777219,
                      "Kr_longitudinal": 16777221, "Kr_transverse": 16777223},
        "short_term": {"Kv": 33554435, "Ks": 33554437,
                       "Kr_longitudinal": 33554439, "Kr_transverse": 33554441},
        "macro_handoff_single": {
            "long_term": {"Kv": 101, "Ks": 102, "Kr": 103},
            "short_term": {"Kv": 201, "Ks": 202, "Kr": 203},
        },
    }


@pytest.mark.parametrize("direction,expected_terms", [
    ("longitudinal", {
        "long_term": {"Kv": 16777217, "Ks": 16777219, "Kr": 16777221},
        "short_term": {"Kv": 33554435, "Ks": 33554437, "Kr": 33554439},
    }),
    ("transverse", {
        "long_term": {"Kv": 16777217, "Ks": 16777219, "Kr": 16777223},
        "short_term": {"Kv": 33554435, "Ks": 33554437, "Kr": 33554441},
    }),
])
def test_all_six_values_use_directional_normal_results_and_keep_provenance(
    synthetic_foundation, direction, expected_terms,
):
    original = deepcopy(synthetic_foundation)
    result = spring_set(synthetic_foundation, direction)
    assert synthetic_foundation == original
    assert result["direction"] == direction
    assert result["terms"] == expected_terms
    components = result["components"]
    assert len(components) == 6
    indexed = {(row["term"], row["component"]): row for row in components}
    assert len(indexed) == 6
    for term, values in expected_terms.items():
        for component, expected in values.items():
            row = indexed[term, component]
            source_component = f"Kr_{direction}" if component == "Kr" else component
            assert row["direction"] == direction
            assert row["value"] == expected
            assert row["source_path"] == f"0500.{term}.{source_component}"
            assert row["precision"] == "Double"
            assert row["unit"] == ("kN·m/rad" if component == "Kr" else "kN/m")


def test_seven_by_nine_foundation_and_width_length_swap():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    dimensions = data["下部構造"]["寸法"]
    dimensions["側面"].update(B7=0, B8=7, B9=0)
    dimensions["正面"].update(W7=0, W8=9, W9=0)
    support = next(layer for layer in data["地盤データ"]["層"] if layer["層番"] == "支持層")
    support["土質区分"] = "砂質土"
    support["変形係数_Ed"] = 165760
    normal = calculate(parse_input(data))
    # Independent literals: A=63, equivalent width=7.937, long kv=202988,
    # short kv=405976; I_long=257.25 and I_trans=425.25 m^4.
    expected_longitudinal = {
        "long_term": {"Kv": 12788244, "Ks": 4262769, "Kr": 52218663},
        "short_term": {"Kv": 25576488, "Ks": 8525475, "Kr": 104437326},
    }
    expected_transverse = {
        "long_term": {"Kv": 12788244, "Ks": 4262769, "Kr": 86320647},
        "short_term": {"Kv": 25576488, "Ks": 8525475, "Kr": 172641294},
    }
    assert spring_set(normal, "longitudinal")["terms"] == expected_longitudinal
    assert spring_set(normal, "transverse")["terms"] == expected_transverse

    swapped_data = deepcopy(data)
    swapped_data["下部構造"]["寸法"]["側面"]["B8"] = 9
    swapped_data["下部構造"]["寸法"]["正面"]["W8"] = 7
    swapped = calculate(parse_input(swapped_data))
    assert spring_set(swapped, "longitudinal")["terms"] == expected_transverse
    assert spring_set(swapped, "transverse")["terms"] == expected_longitudinal


@pytest.mark.parametrize("direction", ["", "b", "vertical", None, True])
def test_unknown_direction_is_rejected_with_path(synthetic_foundation, direction):
    with pytest.raises(InputError, match="direction"):
        spring_set(synthetic_foundation, direction)


@pytest.mark.parametrize("direction", ["longitudinal", "transverse"])
@pytest.mark.parametrize("term", ["long_term", "short_term"])
@pytest.mark.parametrize("component", ["Kv", "Ks", "Kr"])
@pytest.mark.parametrize("bad", ["missing", None, True, float("nan"), float("inf")])
def test_missing_or_invalid_selected_component_has_source_path(
    synthetic_foundation, direction, term, component, bad,
):
    source_component = f"Kr_{direction}" if component == "Kr" else component
    if bad == "missing":
        del synthetic_foundation[term][source_component]
    else:
        synthetic_foundation[term][source_component] = bad
    with pytest.raises(InputError, match=re.escape(f"0500.{term}.{source_component}")):
        spring_set(synthetic_foundation, direction)


@pytest.mark.parametrize("term", ["long_term", "short_term"])
def test_missing_normal_term_does_not_fall_back_to_macro(synthetic_foundation, term):
    del synthetic_foundation[term]
    with pytest.raises(InputError, match=re.escape(f"0500.{term}")):
        spring_set(synthetic_foundation, "longitudinal")
