"""Values that carry their printed digits (ADR-0003).

A calculation report is checked by hand from the printed numbers, so a value
is rounded to the digits it is printed with, and later calculations use that
rounded value. The report never rounds again.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal

MAX_DIGITS = 10
# Enough significant digits for any finite double quantized to MAX_DIGITS places.
_CONTEXT = Context(prec=400)


def _check_digits(digits: object) -> int:
    if type(digits) is not int or not 0 <= digits <= MAX_DIGITS:
        raise ValueError(f"桁数は0～{MAX_DIGITS}の整数が必要です（入力: {digits!r}）")
    return digits


def _check_real(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"有限の数値が必要です（入力: {value!r}）")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"有限の数値が必要です（入力: {value!r}）")
    return result


def round_half_away(value: float, digits: int) -> float:
    """Round the written decimal of *value*, 0.5 away from zero.

    ``repr`` gives the shortest decimal that reads back as the same float,
    which is the number a person sees; 2.675 therefore rounds to 2.68.
    """
    number = _check_real(value)
    places = _check_digits(digits)
    rounded = float(Decimal(repr(number)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP,
                                                   context=_CONTEXT))
    return rounded + 0.0  # turn -0.0 into 0.0


@dataclass(frozen=True)
class Printed:
    """A value exactly as printed: rounded to *digits*, with its unit."""

    value: float
    digits: int
    unit: str

    def __post_init__(self) -> None:
        value = _check_real(self.value)
        _check_digits(self.digits)
        if round_half_away(value, self.digits) != value:
            raise ValueError(f"{value!r} は小数{self.digits}桁に丸められていません")
        object.__setattr__(self, "value", value + 0.0)


@dataclass(frozen=True)
class Precision:
    """How one kind of quantity is printed, e.g. forces in kN to 2 decimals."""

    digits: int
    unit: str

    def __post_init__(self) -> None:
        _check_digits(self.digits)

    def __call__(self, raw: float) -> Printed:
        return Printed(round_half_away(raw, self.digits), self.digits, self.unit)

    def exact(self, value: float) -> Printed:
        """Accept *value* only if it already has no more than the printed digits."""
        number = _check_real(value)
        if round_half_away(number, self.digits) != number:
            raise ValueError(f"小数{self.digits}桁までで入力してください（入力: {value!r}）")
        return Printed(number, self.digits, self.unit)

    def trimmed(self, raw: float) -> Printed:
        """Round to these digits, then print only the digits the value has (150, 52.5, 10.39).

        For values that are exact at these digits, such as table interpolation,
        where padding zeros would suggest a precision that was never rounded to.
        """
        value = round_half_away(raw, self.digits)
        digits = next(places for places in range(self.digits + 1) if round_half_away(value, places) == value)
        return Printed(value, digits, self.unit)

    def total(self, parts: Iterable[Printed]) -> Printed:
        """Sum the printed parts, as a person adding the printed column would."""
        values = []
        for part in parts:
            if part.unit != self.unit:
                raise ValueError(f"単位が異なる値は合計できません: {part.unit} と {self.unit}")
            values.append(part.value)
        return self(math.fsum(values))


# Printed digits of the Example2 calculation documents (.claude/docs/Example橋脚2).
LENGTH = Precision(3, "m")
AREA = Precision(3, "m2")
INERTIA = Precision(5, "m4")
UNIT_WEIGHT = Precision(1, "kN/m3")
PRESSURE = Precision(1, "kN/m2")
LINE_LOAD = Precision(2, "kN/m")
FORCE = Precision(2, "kN")
MOMENT = Precision(2, "kN m")
COEFFICIENT = Precision(3, "")
