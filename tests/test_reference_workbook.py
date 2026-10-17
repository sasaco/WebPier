"""Acceptance against Microsoft Excel 16 recalculation, without Excel at test time.

The golden data was obtained from a read-only temporary copy of the original
0500 workbook with macros/events disabled and links not updated.  These tests
compare numerical outcomes rather than repeating the Python equations.
"""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src import calculate, parse_input

ROOT = Path(__file__).resolve().parents[1]
ORACLE = json.loads((Path(__file__).parent / "fixtures" / "excel_oracle.json").read_text(encoding="utf-8"))
BASE_INPUT = json.loads((ROOT / "pre" / "input.json").read_text(encoding="utf-8-sig"))


def oracle_input(case):
    data = deepcopy(BASE_INPUT)
    given = case["input"]
    dims = data["下部構造"]["寸法"]
    dims["側面"].update(B7=0, B8=given["b"], B9=0)
    dims["正面"].update(W7=0, W8=given["l"], W9=0)
    support = next(layer for layer in data["地盤データ"]["層"] if layer["層番"] == "支持層")
    support.update({"土質区分": given["soil"], "内部摩擦角_φd": given["phi"], "変形係数_Ed": given["ed"]})
    return parse_input(data)


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case"])
def test_all_spring_values_match_excel_recalculation(case):
    result = calculate(oracle_input(case))
    expected = case["values"]
    for field, excel_field in {
        "B": "b", "L": "l", "area": "area", "equivalent_width": "equivalent_width",
        "inertia_longitudinal": "inertia_longitudinal", "inertia_transverse": "inertia_transverse",
    }.items():
        assert result["foundation"][field] == expected[excel_field], field
    for term, suffix in (("long_term", "long"), ("short_term", "short")):
        for field in ("kv", "Kv", "ks", "Ks", "Kr_longitudinal", "Kr_transverse"):
            assert result[term][field] == expected[f"{field}_{suffix}"], (term, field)


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda case: case["case"])
def test_public_kr_is_transverse_and_outgoing_values_are_single(case):
    result = calculate(oracle_input(case))
    for term, japanese_term in (("long_term", "長期"), ("short_term", "短期")):
        for field in ("Kv", "Ks", "Kr"):
            assert result["macro_handoff_single"][term][field] == case["public_single"][field + japanese_term]
        assert result[term]["Kr_transverse"] == case["public_ranges"]["Kr" + japanese_term]
        assert result[term]["Kr_longitudinal"] != case["public_ranges"]["Kr" + japanese_term]


def test_bearing_factors_follow_supplied_table_instead_of_historical_excel_constants():
    case = next(case for case in ORACLE["cases"] if case["case"] == "changed_dimensions_and_phi")
    assert case["input"]["phi"] == 25
    result = calculate(oracle_input(case))
    assert result["model"]["bearing_n_gamma"] == 3.6
    assert result["model"]["bearing_n_q"] == 4.8
    # Preserve the historical oracle as evidence of the superseded fixed values.
    for suffix in ("long", "short"):
        assert case["values"][f"N_gamma_{suffix}"] == 45
        assert case["values"][f"N_q_{suffix}"] == 31


def test_saved_pdf_and_current_input_are_distinct_reference_cases():
    cases = {case["case"]: case for case in ORACLE["cases"]}
    saved = calculate(oracle_input(cases["saved_andesite"]))
    current = calculate(oracle_input(cases["current_input_sand"]))
    assert saved["model"]["coefficient"] == 5.1
    assert current["model"]["coefficient"] == 6.9
    assert saved["long_term"]["Kv"] == 1713058
    assert current["long_term"]["Kv"] == 3657924
    # Cell Double values in the report must not be replaced by the VBA handoff.
    assert current["short_term"]["Kr_transverse"] == 29872885
    assert current["macro_handoff_single"]["short_term"]["Kr"] == 29872884
