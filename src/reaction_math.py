"""Excel-compatible numerical helpers specific to the 0600 worksheets."""

from decimal import Decimal, ROUND_HALF_UP, localcontext
import math

from .inputs import InputError


VBA_SINGLE_MAX = float.fromhex("0x1.fffffep+127")


def excel_round(value: float, places: int = 0) -> float | int:
    """ROUND away from zero after normalizing Excel's 15 significant digits.

    For example, the 0600 expression evaluating to 639.9749999999999 in Python
    rounds to 639.98 in Excel. Magnitudes are limited to the finite VBA Single
    range used by the downstream load handoff, not every Excel ROUND input.
    This helper does not change the 0500 arithmetic.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError("0600 ROUND: 有限の数値が必要です")
    if type(places) is not int:
        raise InputError("0600 ROUND: 桁数は整数が必要です")
    try:
        number = float(value)
        if not math.isfinite(number):
            raise InputError("0600 ROUND: 有限の数値が必要です")
        if abs(number) > VBA_SINGLE_MAX:
            raise InputError("0600 ROUND: 入力がVBA Singleの有限範囲を超えています")
        with localcontext() as context:
            normalized = Decimal(format(number, ".15g"))
            integer_digits = max(1, normalized.adjusted() + 1)
            context.prec = max(context.prec, integer_digits + max(places, 0) + 2)
            rounded = normalized.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
            return int(rounded) if places == 0 else float(rounded)
    except (ArithmeticError, ValueError) as exc:
        raise InputError("0600 ROUND: 入力または丸め結果が数値範囲を超えています") from exc
