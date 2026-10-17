"""Properties of printed values (ADR-0003, decision 15): one rounding, half away from zero, on the written decimal."""

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext

from hypothesis import given, strategies as st

from webpier.core.printed import MAX_DIGITS, Precision, Printed, round_half_away

DIGITS = st.integers(min_value=0, max_value=MAX_DIGITS)
# Values a calculation report holds; ties such as 0.125 are drawn on purpose as short decimals.
REALS = st.one_of(
    st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.decimals(min_value=-10**6, max_value=10**6, places=4, allow_nan=False, allow_infinity=False).map(float),
    st.integers(min_value=-10**6, max_value=10**6).map(lambda value: value / 1000 + 0.0005),
)


def half_up(value: float, digits: int) -> Decimal:
    """Rounding by hand: the written decimal of *value*, 0.5 away from zero."""
    with localcontext() as context:
        context.prec = 500
        return Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


@given(REALS, DIGITS)
def test_round_half_away_is_the_hand_rounding_of_the_written_decimal(value, digits):
    assert round_half_away(value, digits) == float(half_up(value, digits))


@given(REALS, DIGITS)
def test_rounding_twice_changes_nothing(value, digits):
    once = round_half_away(value, digits)
    assert round_half_away(once, digits) == once


@given(REALS, DIGITS)
def test_rounding_is_symmetric_in_sign_and_never_gives_negative_zero(value, digits):
    rounded = round_half_away(value, digits)
    assert round_half_away(-value, digits) == -rounded
    for result in (rounded, round_half_away(-value, digits)):
        assert result != 0 or math.copysign(1.0, result) == 1.0


@given(REALS, DIGITS)
def test_a_precision_prints_exactly_its_digits(value, digits):
    printed = Precision(digits, "m")(value)
    assert printed.digits == digits and printed.unit == "m"
    assert Decimal(repr(printed.value)).normalize().as_tuple().exponent >= -digits
    assert float(f"{printed.value:.{digits}f}") == printed.value
    assert abs(Decimal(repr(printed.value)) - Decimal(repr(value))) <= Decimal("0.5").scaleb(-digits)
    assert Precision(digits, "m").exact(printed.value) == printed


@given(st.lists(REALS, max_size=12), st.integers(min_value=0, max_value=5))
def test_a_total_is_the_sum_of_the_printed_parts(values, digits):
    precision = Precision(digits, "kN")
    parts = [precision(value) for value in values]
    by_hand = sum((Decimal(repr(part.value)) for part in parts), Decimal(0))
    assert precision.total(parts) == Printed(float(by_hand), digits, "kN")


@given(REALS, DIGITS)
def test_trimmed_never_prints_more_digits_than_the_precision_or_a_padding_zero(value, digits):
    precision = Precision(digits, "")
    trimmed = precision.trimmed(value)
    assert trimmed.value == precision(value).value
    assert 0 <= trimmed.digits <= digits
    if trimmed.digits:
        assert round_half_away(trimmed.value, trimmed.digits - 1) != trimmed.value
