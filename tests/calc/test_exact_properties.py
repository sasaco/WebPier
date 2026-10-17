"""Exact decimal results are rounded once to their printed digits (ADR-0003: one rounding, half away from zero)."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest
from hypothesis import given, strategies as st

from webpier.calc._exact import d, put, total
from webpier.core.printed import Precision, Printed


def by_hand(exact: Decimal, digits: int) -> float:
    with localcontext() as context:
        context.prec = 500
        return float(exact.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


@st.composite
def near_ties(draw):
    """A quotient's 28 digits can end just below or above a printed tie such as 0.1665."""
    digits = draw(st.integers(min_value=0, max_value=5))
    units = draw(st.integers(min_value=-10**7, max_value=10**7))
    offset = draw(st.integers(min_value=-1000, max_value=1000))
    exponent = draw(st.integers(min_value=15, max_value=26))
    tie = (Decimal(units) + Decimal("0.5")).scaleb(-digits)
    return tie + Decimal(offset).scaleb(-exponent), digits


EXACT = st.one_of(near_ties(), st.tuples(
    st.decimals(min_value=-10**9, max_value=10**9, places=12, allow_nan=False, allow_infinity=False),
    st.integers(min_value=0, max_value=5)))


@given(EXACT)
def test_an_exact_result_is_rounded_once(case):
    exact, digits = case
    assert put(Precision(digits, "kN"), exact) == Printed(by_hand(exact, digits), digits, "kN")


def test_a_value_just_below_a_tie_is_not_rounded_up_through_a_binary_double():
    # Found by hypothesis (minimal: 0.49999999999999999 to 0 digits gave 1): the double nearest
    # 0.16649999999999999999 is 0.1665, which then rounded to 0.167.
    assert put(Precision(0, ""), Decimal("0.49999999999999999")).value == 0
    assert put(Precision(3, ""), Decimal("0.16649999999999999999")).value == 0.166
    assert put(Precision(3, ""), Decimal("-0.16649999999999999999")).value == -0.166
    assert put(Precision(3, ""), Decimal("0.1665")).value == 0.167


def test_a_result_beyond_a_double_is_refused_as_before():
    with pytest.raises(ValueError, match="有限の数値"):
        put(Precision(2, "kN"), Decimal("1e400"))


@given(st.lists(st.decimals(min_value=-10**6, max_value=10**6, places=3, allow_nan=False, allow_infinity=False),
                max_size=8))
def test_printed_numbers_read_and_add_as_the_decimals_a_person_sees(values):
    printed = [Printed(float(value), 3, "m") for value in values]
    assert [d(item) for item in printed] == [Decimal(repr(float(value))) for value in values]
    assert total(printed) == sum((Decimal(repr(float(value))) for value in values), Decimal(0))
