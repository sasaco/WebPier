"""Exact decimal arithmetic on printed numbers (ADR-0003).

A person checks the report with the printed numbers, so a product such as
0.222 × 0.75 must give 0.1665 and round to 0.167. Binary floating point can land
just below such a tie, so the formulas of this package are evaluated in Decimal
from the printed values and rounded once, by the Precision of the result.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from ..core.printed import Precision, Printed

Number = Printed | float | int


def d(number: Number) -> Decimal:
    """The decimal a person reads: a Printed value, a float or an integer constant."""
    raw = number.value if isinstance(number, Printed) else number
    return Decimal(raw) if isinstance(raw, int) else Decimal(repr(float(raw)))


def put(precision: Precision, exact: Decimal) -> Printed:
    """Round an exact result to its printed digits."""
    return precision(float(exact))


def total(numbers: Iterable[Number]) -> Decimal:
    return sum((d(number) for number in numbers), Decimal(0))
