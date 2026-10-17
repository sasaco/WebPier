from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src import InputError, calculate, parse_input
from src.calculator import excel_round, vba_single

PROJECT = Path(__file__).resolve().parents[1]
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = PROJECT / "tests" / "fixtures" / "baseline_input.json"


@pytest.fixture
def data():
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_p7_input_is_computed_and_not_changed(data):
    original = copy.deepcopy(data)
    result = calculate(parse_input(data))
    assert data == original
    assert result["support_layer"]["soil_type"] == "砂質土"
    assert result["long_term"]["kv"] == 95011
    assert result["long_term"]["Kv"] == 3657924  # Exact x.5 rounds upwards.
    assert result["short_term"]["Kr_transverse"] == 29872885
    assert result["macro_handoff_single"]["short_term"]["Kr"] == 29872884


@pytest.mark.parametrize("value,places,expected", [
    (3657923.5, 0, 3657924), (-1.5, 0, -2), (2.5, 0, 3),
    (1.2345, 3, 1.235), (-1.2345, 3, -1.235),
])
def test_excel_round(value, places, expected):
    assert excel_round(value, places) == expected


def test_updates_use_modulus_dimensions_and_surface_formula(data):
    before = calculate(parse_input(data))
    data["地盤データ"]["層"][1]["変形係数_Ed"] *= 2
    data["下部構造"]["寸法"]["側面"]["B8"] = 6.125
    data["下部構造"]["寸法"]["高さ"]["H6"] = 2.5
    data["下部構造"]["土かぶり"]["起点側_df1"] = 1.5
    data["下部構造"]["土かぶり"]["終点側_df2"] = 2.5
    data["地盤データ"]["層"][0]["層厚"] = 99
    after = calculate(parse_input(data))
    assert after["foundation"]["area"] == 42.875
    assert after["layers"][0]["thickness"] == 4.0
    assert "99.0" in after["warnings"][0]
    assert after["long_term"]["Kv"] != before["long_term"]["Kv"]


def test_width_accumulation_uses_single_each_time(data):
    data["下部構造"]["寸法"]["側面"].update(B7=0.1, B8=5.4, B9=0.1)
    result = calculate(parse_input(data))
    expected = vba_single(vba_single(vba_single(0.1) + 5.4) + 0.1)
    assert result["foundation"]["B"] == expected


def test_blank_is_not_zero_in_report_data(data):
    result = calculate(parse_input(data))
    assert result["layers"][0]["n_value"] == 0
    assert result["layers"][0]["deformation_modulus"] is None
    assert result["support_layer"]["thickness"] is None


@pytest.mark.parametrize("field,value", [
    ("変形係数_Ed", None), ("変形係数_Ed", 0), ("変形係数_Ed", -1),
    ("変形係数_Ed", float("nan")), ("変形係数_Ed", float("inf")),
    ("変形係数_Ed", True), ("変形係数_Ed", "68600"),
    ("内部摩擦角_φd", 90),
])
def test_invalid_support_values_are_rejected(data, field, value):
    data["地盤データ"]["層"][1][field] = value
    with pytest.raises(InputError):
        parse_input(data)


@pytest.mark.parametrize("case", ["missing", "duplicate", "zero_area", "pile", "bad_version", "too_many", "huge", "tiny"])
def test_invalid_structure_is_rejected(data, case):
    if case == "missing":
        data["地盤データ"]["層"][1]["層番"] = "別層"
    elif case == "duplicate":
        data["地盤データ"]["層"].append(copy.deepcopy(data["地盤データ"]["層"][1]))
    elif case == "zero_area":
        data["下部構造"]["寸法"]["側面"]["B8"] = 0
    elif case == "pile":
        data["下部構造"]["杭種"]["選択値"] = "場所打ち杭"
    elif case == "bad_version":
        data["schema_version"] = True
    elif case == "too_many":
        data["地盤データ"]["層"] += [copy.deepcopy(data["地盤データ"]["層"][0])] * 10
    elif case == "huge":
        data["下部構造"]["寸法"]["側面"]["B8"] = 1e100
    elif case == "tiny":
        data["下部構造"]["寸法"]["側面"]["B8"] = 1e-8
    with pytest.raises(InputError):
        calculate(parse_input(data))


def test_support_selection_is_by_label_not_position(data):
    middle = copy.deepcopy(data["地盤データ"]["層"][0])
    middle["層番"] = "中間層"
    middle["変形係数_Ed"] = 12345
    data["地盤データ"]["層"].insert(1, middle)
    result = calculate(parse_input(data))
    assert result["support_layer"]["deformation_modulus"] == 68600
    assert result["long_term"]["kv"] == 95011


def test_unused_superstructure_is_not_a_dependency(data):
    for key in ("上部構造", "上部工反力"):
        data.pop(key)
    assert calculate(parse_input(data))["long_term"]["kv"] == 95011
