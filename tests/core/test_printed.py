"""Printed values: the number on paper is the number used downstream (ADR-0003)."""

import math

import pytest

from webpier.core.printed import FORCE, LENGTH, MOMENT, Precision, Printed, round_half_away


@pytest.mark.parametrize("value,digits,expected", [
    (0.125, 2, 0.13),
    (-0.125, 2, -0.13),
    (2.675, 2, 2.68),      # binary 2.67499999…; the written number is rounded
    (2.665, 2, 2.67),
    (639.975, 2, 639.98),
    (12.5, 0, 13.0),
    (-12.5, 0, -13.0),
    (1.0049999, 2, 1.0),
    (0.0, 3, 0.0),
    (123456789.125, 2, 123456789.13),
])
def test_round_half_away_from_zero_on_the_written_decimal(value, digits, expected):
    assert round_half_away(value, digits) == expected


def test_round_never_returns_negative_zero():
    assert math.copysign(1.0, round_half_away(-0.0001, 2)) == 1.0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_round_rejects_non_finite(value):
    with pytest.raises(ValueError):
        round_half_away(value, 2)


@pytest.mark.parametrize("digits", [-1, 11, 1.5, True])
def test_round_rejects_invalid_digits(digits):
    with pytest.raises(ValueError):
        round_half_away(1.0, digits)


def test_precision_rounds_and_labels_the_value():
    value = FORCE(312.6049)
    assert value == Printed(312.6, 2, "kN")
    assert (value.value, value.digits, value.unit) == (312.6, 2, "kN")


def test_printed_cannot_hold_more_digits_than_it_prints():
    with pytest.raises(ValueError):
        Printed(0.125, 2, "kN")


@pytest.mark.parametrize("value", [math.nan, math.inf, True, "1"])
def test_printed_requires_a_finite_real_number(value):
    with pytest.raises(ValueError):
        Printed(value, 2, "kN")


def test_total_adds_the_printed_parts_not_the_raw_parts():
    parts = [FORCE(0.125)] * 3
    assert [part.value for part in parts] == [0.13, 0.13, 0.13]
    assert FORCE.total(parts).value == 0.39      # raw sum 0.375 would print 0.38


def test_total_cancels_binary_noise_of_the_sum():
    parts = [FORCE(0.1), FORCE(0.2)]
    assert FORCE.total(parts).value == 0.3


def test_total_of_nothing_is_zero():
    assert MOMENT.total([]).value == 0.0


def test_total_rejects_mixed_units():
    with pytest.raises(ValueError):
        FORCE.total([FORCE(1.0), LENGTH(1.0)])


def test_precision_accepts_only_values_already_at_its_digits():
    assert LENGTH.exact(2.952).value == 2.952
    with pytest.raises(ValueError, match="小数3桁"):
        LENGTH.exact(2.9520833333333334)


def test_precision_definition_is_validated():
    with pytest.raises(ValueError):
        Precision(-1, "m")
    assert Precision(0, "kN/m").digits == 0


def test_round_handles_the_whole_float_range():
    assert round_half_away(1.7976931348623157e308, 2) == 1.7976931348623157e308
    assert round_half_away(5e-324, 3) == 0.0
