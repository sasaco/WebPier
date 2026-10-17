"""Concrete Ec from the RcDan table (decision 25): Example2 8-2 / 9-2 and hand interpolation."""

from decimal import Decimal

import pytest

from reaction_support import pier, q
from webpier.calc.materials import EC_EXPONENT, EC_TABLE, calculate_materials, concrete
from webpier.core.errors import InputError
from webpier.core.printed import Precision

STRENGTH = Precision(1, "N/mm2")
REBAR = "鉄筋/{part}/concrete_strength_mpa"
TABLE = ((18, 22), (24, 25), (30, 28), (40, 31), (50, 33), (60, 35), (70, 37), (80, 38))  # f'ck N/mm2, Ec kN/mm2


def hand_mantissa(fck: str) -> tuple[Decimal, tuple[int, int], tuple[int, int]]:
    """Ec / 10^7 kN/m2 by linear interpolation in the table, rounded to 2 decimals."""
    f = Decimal(fck)
    for (f0, e0), (f1, e1) in zip(TABLE, TABLE[1:]):
        if f <= f1:
            ec = Decimal(e0) + Decimal(e1 - e0) * (f - f0) / (f1 - f0)  # kN/mm2
            return q(ec / 10, 2), (f0, e0), (f1, e1)
    raise AssertionError(fck)


def test_table_is_rcdan_ec_civil_list():
    assert [(point.strength.value, point.modulus.value) for point in EC_TABLE] == [
        (float(f), float(e)) for f, e in TABLE]
    assert {point.modulus.unit for point in EC_TABLE} == {"kN/mm2"}
    assert EC_EXPONENT == 7


def test_example2_8_2_body_27_gives_2_65e7():
    # 08 p.8-2 (and 09 p.9-2 for the body and the footing): f'ck 27.0, Ec = 2.65 × 10^7 kN/m2.
    result = concrete(STRENGTH.exact(27.0), "鉄筋.柱.concrete_strength_mpa")
    assert (result.strength.value, result.strength.digits) == (27.0, 1)
    assert (result.modulus.value, result.modulus.digits) == (2.65, 2)
    assert result.ec == 26_500_000.0
    assert (result.lower.strength.value, result.lower.modulus.value) == (24.0, 25.0)
    assert (result.upper.strength.value, result.upper.modulus.value) == (30.0, 28.0)


@pytest.mark.parametrize("fck", ["18.0", "18.1", "24.0", "24.1", "27.3", "35.0", "45.5", "79.9", "80.0"])
def test_interpolation_by_hand(fck):
    mantissa, lower, upper = hand_mantissa(fck)
    result = concrete(STRENGTH.exact(float(fck)), "path")
    assert Decimal(repr(result.modulus.value)) == mantissa
    assert (result.lower.strength.value, result.lower.modulus.value) == lower
    assert (result.upper.strength.value, result.upper.modulus.value) == upper
    assert result.ec == float(mantissa * 10 ** 7)


def test_half_up_tie_27_3():
    # 25 + 3 × 3.3 / 6 = 26.65 kN/mm2 -> 2.665 -> 2.67 (0.5 away from zero, ADR-0003)
    assert concrete(STRENGTH.exact(27.3), "path").modulus.value == 2.67


@pytest.mark.parametrize("fck", [17.9, 80.1, 0.1, 120.0])
def test_outside_the_table_is_an_input_error(fck):
    with pytest.raises(InputError, match=r"鉄筋\.梁\.concrete_strength_mpa.*18.*80"):
        concrete(STRENGTH.exact(fck), "鉄筋.梁.concrete_strength_mpa")


def test_parts_follow_their_own_input():
    result = calculate_materials(pier(**{REBAR.format(part="梁"): 24.0, REBAR.format(part="柱"): 30.0,
                                         REBAR.format(part="フーチング"): 40.0}))
    assert (result.beam.strength.value, result.beam.modulus.value) == (24.0, 2.5)
    assert (result.column.strength.value, result.column.modulus.value) == (30.0, 2.8)
    assert (result.footing.strength.value, result.footing.modulus.value) == (40.0, 3.1)


def test_range_error_names_the_part():
    with pytest.raises(InputError, match=r"鉄筋\.フーチング\.concrete_strength_mpa"):
        calculate_materials(pier(**{REBAR.format(part="フーチング"): 81.0}))
