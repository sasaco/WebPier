"""The one place that turns values into printed text (reporting-layer conventions).

A Printed value is written at exactly its digits. The digits are the
calculator's; nothing here rounds or chooses a number of places. Thousand
separators, the minus sign and the unit notation are presentation choices.
"""

from __future__ import annotations

import math
from decimal import Context, Decimal, Inexact

from gridlayoutpdf import MathNode

from ..core.printed import Printed
from .equations import script

# Every quantize must be exact; an Inexact trap means a value would be rounded.
_EXACT = Context(prec=400, traps=[Inexact])


def printed(value: Printed, *, thousands: bool = False) -> str:
    """The written decimal of *value* at its digits, e.g. 7.937, 257.250000, 4,262,769."""
    if not isinstance(value, Printed):
        raise TypeError(f"Printed が必要です（入力: {value!r}）")
    # repr is the decimal a person reads (core.printed.round_half_away uses it too);
    # the binary expansion of 10000000.1 would print as ...0999999996 at 10 places.
    decimal = Decimal(repr(value.value)).quantize(Decimal(1).scaleb(-value.digits), context=_EXACT)
    return format(decimal, ",f" if thousands else "f")


def constant(value: float) -> str:
    """A table constant of an equation (6.9, ρ = 0.5) as written: its shortest decimal."""
    if type(value) is not float:
        raise TypeError(f"定数は float が必要です（入力: {value!r}）")
    if not math.isfinite(value):
        raise ValueError(f"定数は有限の値が必要です（入力: {value!r}）")
    return repr(value)


def _power(base: str, exponent: str) -> MathNode:
    return script(base, superscript=exponent)


_UNITS: dict[str, str | tuple[str, str]] = {
    "m": "m",
    "kN": "kN",
    "kN m": "kN・m",
    "m3": ("m", "3"),
    "kN/m": "kN/m",
    "kN m/rad": "kN・m/rad",
    "m2": ("m", "2"),
    "m4": ("m", "4"),
    "kN/m2": ("kN/m", "2"),
    "kN/m3": ("kN/m", "3"),
    "N/mm2": ("N/mm", "2"),
    "kN/mm2": ("kN/mm", "2"),
}


def unit(text: str) -> str | MathNode:
    """How a unit of core.printed is written; exponents become superscripts."""
    try:
        written = _UNITS[text]
    except KeyError:
        raise ValueError(f"表記の決まっていない単位です: {text!r}") from None
    return written if isinstance(written, str) else _power(*written)
