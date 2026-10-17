"""0500 ground springs: Example2 04 pp.4-1–4-3 and hand calculations with Decimal."""

import json
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from webpier.calc.foundation import calculate_foundation
from webpier.core.errors import InputError
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
EXAMPLE2 = json.loads((FIXTURES / "example2" / "foundation.json").read_text(encoding="utf-8"))["printed"]


def pier(**changes):
    document = deepcopy(CURRENT)
    for path, value in changes.items():
        node = document
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    return parse_input(document)


def q(value, digits):
    """Hand rounding, 0.5 away from zero, without the implementation."""
    return Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def test_example2_springs_as_printed():
    result = calculate_foundation(pier())
    assert (result.b.value, result.l.value, result.area.value, result.width.value) == (7.0, 9.0, 63.0, 7.937)
    assert (result.inertia_longitudinal.value, result.inertia_transverse.value) == (257.25, 425.25)
    assert (result.coefficient, result.exponent_text) == (6.9, "-1/2")
    assert (result.n_gamma.value, result.n_q.value) == (150, 85)
    for term in ("long_term", "short_term"):
        springs = getattr(result, term)
        for key, value in EXAMPLE2[term].items():
            assert getattr(springs, key).value == value, (term, key)


def test_printed_digits_and_units():
    result = calculate_foundation(pier())
    assert (result.width.digits, result.inertia_longitudinal.digits, result.long_term.kv.digits) == (3, 6, 0)
    assert (result.long_term.kv.unit, result.long_term.Kv.unit, result.long_term.Kr_transverse.unit) == (
        "kN/m3", "kN/m", "kN m/rad")


def hand(b, l, ed, coefficient, exponent, rho):
    area = q(Decimal(str(b)) * Decimal(str(l)), 3)
    width = q(area.sqrt(), 3)
    kv = q(Decimal(repr(coefficient * rho * ed * float(width) ** exponent)), 0)
    ks = q(kv / 3, 0)
    iv_l = q(Decimal(str(l)) * Decimal(str(b)) ** 3 / 12, 6)
    iv_t = q(Decimal(str(b)) * Decimal(str(l)) ** 3 / 12, 6)
    return {"kv": kv, "ks": ks, "Kv": q(kv * area, 0), "Ks": q(ks * area, 0),
            "Kr_longitudinal": q(kv * iv_l, 0), "Kr_transverse": q(kv * iv_t, 0)}


@pytest.mark.parametrize("soil,coefficient,exponent", [
    ("粘性土", 3.8, -1.0),
    ("砂質土と粘性土の互層", 5.1, -0.75),
    ("砂質土", 6.9, -0.5),
])
def test_each_soil_equation_by_hand(soil, coefficient, exponent):
    result = calculate_foundation(pier(**{
        "地盤データ/層/1/土質区分": soil, "地盤データ/層/1/変形係数_Ed": 50000,
        "下部構造/寸法/側面/B7": 1.5, "下部構造/寸法/側面/B9": 1.25, "下部構造/寸法/正面/W7": 2.0}))
    b, l = 1.5 + 2.7 + 1.25, 2.0 + 4.5 + 2.25
    for term, rho in (("long_term", 0.5), ("short_term", 1.0)):
        springs = getattr(result, term)
        for key, value in hand(b, l, 50000, coefficient, exponent, rho).items():
            assert Decimal(repr(getattr(springs, key).value)) == value, (soil, term, key)


def test_springs_use_the_printed_width_and_area():
    result = calculate_foundation(pier())
    # 63.000 → √ = 7.93725… printed 7.937; kv must come from 7.937, not 7.93725.
    from_printed = q(Decimal(repr(6.9 * 0.5 * 165760 * 7.937 ** -0.5)), 0)
    assert Decimal(repr(result.long_term.kv.value)) == from_printed


@pytest.mark.parametrize("phi,n_gamma,n_q", [
    (25.0, 3.6, 4.8), (37.5, 52.5, 35.0), (31.3, 10.39, 10.16), (41.9, 148.0, 83.8), (42.0, 150, 85), (60.0, 150, 85),
])
def test_bearing_factors_interpolate_the_flat_ground_table(phi, n_gamma, n_q):
    result = calculate_foundation(pier(**{"地盤データ/層/1/内部摩擦角_φd": phi}))
    assert (result.n_gamma.value, result.n_q.value) == (n_gamma, n_q)


def test_surface_thickness_is_derived_and_printed():
    result = calculate_foundation(pier())
    assert result.surface_thickness.value == 4.7          # H6 2.7 + H5 0 + min(2.0, 2.0)
    result = calculate_foundation(pier(**{"下部構造/土かぶり/終点側_df2": 1.08}))
    assert result.surface_thickness.value == 3.78


def test_huge_inputs_are_an_input_error_not_a_crash():
    with pytest.raises(InputError):
        calculate_foundation(pier(**{"地盤データ/層/1/変形係数_Ed": 10 ** 308}))
