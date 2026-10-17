"""Ground model checks against the supplied bearing-factor table and Example2."""

from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import re

import pytest
from pypdf import PdfReader

from src import InputError, calculate, parse_input
from src.report import render_report

PROJECT = Path(__file__).resolve().parents[1]

# Transcribed from 解説表13.2.2.3-2, independently of calculation code.
BEARING_TABLE = [
    (25, 3.6, 4.8), (26, 4.0, 5.2), (27, 4.5, 5.6),
    (28, 5.0, 6.1), (29, 6.2, 7.1), (30, 7.7, 8.3),
    (31, 9.7, 9.8), (32, 12, 11), (33, 15, 14),
    (34, 20, 17), (35, 26, 20), (36, 34, 25),
    (37, 45, 31), (38, 60, 39), (39, 80, 50),
    (40, 100, 64), (41, 130, 73), (42, 150, 85),
]


@pytest.fixture
def example2_data():
    data = json.loads((PROJECT / "pre/input.json").read_text(encoding="utf-8-sig"))
    dims = data["下部構造"]["寸法"]
    dims["側面"].update(B7=0, B8=7, B9=0)
    dims["正面"].update(W7=0, W8=9, W9=0)
    support = next(layer for layer in data["地盤データ"]["層"] if layer["層番"] == "支持層")
    support.update({"土質区分": "砂礫", "内部摩擦角_φd": 42.2, "変形係数_Ed": 165760})
    return data


def support_row(data):
    return next(layer for layer in data["地盤データ"]["層"] if layer["層番"] == "支持層")


@pytest.mark.parametrize("phi,n_gamma,n_q", BEARING_TABLE + [
    (25.25, 3.7, 4.9), (25.5, 3.8, 5.0),
    (37.25, 48.75, 33.0), (37.5, 52.5, 35), (41.5, 140, 79),
    (42.2, 150, 85), (89.9, 150, 85),
])
def test_support_factors_follow_table_with_linear_interpolation(example2_data, phi, n_gamma, n_q):
    support_row(example2_data)["内部摩擦角_φd"] = phi
    result = calculate(parse_input(example2_data))
    assert result["model"]["bearing_n_gamma"] == pytest.approx(n_gamma)
    assert result["model"]["bearing_n_q"] == pytest.approx(n_q)


@pytest.mark.parametrize("phi", [None, 24.9, -1, 90, float("nan"), float("inf"), True, "37"])
def test_invalid_support_angle_is_rejected_during_parsing(example2_data, phi):
    support_row(example2_data)["内部摩擦角_φd"] = phi
    with pytest.raises(InputError, match="内部摩擦角"):
        parse_input(example2_data)


def test_missing_support_angle_is_rejected(example2_data):
    del support_row(example2_data)["内部摩擦角_φd"]
    with pytest.raises(InputError, match="内部摩擦角"):
        parse_input(example2_data)


@pytest.mark.parametrize("phi", [None, 24.9, 90, float("nan"), float("inf"), True, "37"])
def test_calculation_rejects_unsupported_angle_in_direct_design_input(example2_data, phi):
    inputs = parse_input(example2_data)
    inputs = replace(inputs, layers=tuple(
        replace(layer, friction_angle=phi) if layer.name == "支持層" else layer
        for layer in inputs.layers
    ))
    with pytest.raises(InputError, match="内部摩擦角"):
        calculate(inputs)


def test_gravel_uses_sand_formula_and_matches_all_example2_spring_values(example2_data):
    original = copy.deepcopy(example2_data)
    result = calculate(parse_input(example2_data))
    assert example2_data == original
    assert result["support_layer"]["soil_type"] == "砂礫"
    assert result["model"]["coefficient"] == 6.9
    assert result["model"]["exponent"] == -0.5
    assert not any("砂礫" in warning for warning in result["warnings"])
    assert result["long_term"] == {
        "kv": 202988, "Kv": 12788244, "ks": 67663, "Ks": 4262769,
        "Kr_longitudinal": 52218663, "Kr_transverse": 86320647,
    }
    assert result["short_term"] == {
        "kv": 405976, "Kv": 25576488, "ks": 135325, "Ks": 8525475,
        "Kr_longitudinal": 104437326, "Kr_transverse": 172641294,
    }
    support_row(example2_data)["土質区分"] = "砂質土"
    sand = calculate(parse_input(example2_data))
    assert sand["long_term"] == result["long_term"]
    assert sand["short_term"] == result["short_term"]


def test_factors_use_support_layer_by_name_and_its_phi(example2_data):
    layers = example2_data["地盤データ"]["層"]
    middle = copy.deepcopy(layers[0])
    middle.update({"層番": "中間層", "内部摩擦角_φd": 25})
    layers.insert(1, middle)
    support_row(example2_data)["内部摩擦角の上限値"] = 37
    result = calculate(parse_input(example2_data))
    assert result["model"]["bearing_n_gamma"] == 150
    assert result["model"]["bearing_n_q"] == 85


@pytest.mark.parametrize("phi,n_gamma,n_q", [(25.5, "3.8", "5"), (37.5, "52.5", "35")])
def test_pdf_retains_interpolated_factors_for_both_loading_conditions(example2_data, tmp_path, phi, n_gamma, n_q):
    support_row(example2_data)["内部摩擦角_φd"] = phi
    result = calculate(parse_input(example2_data))
    pdf = tmp_path / "ground-model.pdf"
    render_report(result, pdf)
    # Pages vary with content; read the factor rows wherever they flow.
    text = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
    factor_text = text.split("支持層の支持力係数", 1)[1].split("5.2", 1)[0]
    factor_rows = re.findall(
        r"N\s*γ\s*=\s*(\d+(?:\.\d+)?)\s*,\s*N\s*q\s*=\s*(\d+(?:\.\d+)?)\s*(地震時を除く|地震時)",
        factor_text,
    )
    assert factor_rows == [(n_gamma, n_q, "地震時を除く"), (n_gamma, n_q, "地震時")]


def test_bearing_factor_provenance_identifies_table_and_interpolation(example2_data):
    provenance = calculate(parse_input(example2_data))["provenance"]["bearing_factors"]
    assert "13.2.2.3-2" in provenance
    assert "線形補間" in provenance
    assert "固定値" not in provenance
