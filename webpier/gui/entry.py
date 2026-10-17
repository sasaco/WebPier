"""Turn the text typed into a cell into the value saved in the input JSON, and back (decisions 6, 17).

A number is rounded to its field's printed digits at entry (0.5 away from zero), so the cell shows and the file
stores exactly the value the calculation prints. The digits, sign rules, ranges and choices come from the field
table (webpier/inputs/fields.py); nothing here restates them. A blank is saved as null: an unfinished input can
be saved, and the editor marks the blanks a value is needed for.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from ..core.errors import InputError
from ..core.printed import round_half_away
from ..core.reader import Reader
from ..inputs.fields import Field

_INTEGER = re.compile(r"[+-]?\d+")


class EntryError(ValueError):
    """The text cannot be entered into this field; the message says why."""


def _normalized(text: str) -> str:
    # Full-width digits and the minus sign of Japanese input.
    return unicodedata.normalize("NFKC", text).replace("−", "-").strip()


def _number(spec: Field, text: str) -> int | float:
    try:
        raw = float(text)
    except ValueError:
        raise EntryError("数値を入力してください") from None
    if not math.isfinite(raw):
        raise EntryError("数値を入力してください")
    assert spec.precision is not None
    value = round_half_away(raw, spec.precision.digits)
    if spec.sign == "positive" and value <= 0:
        raise EntryError("正の数値が必要です")
    if spec.sign == "nonnegative" and value < 0:
        raise EntryError("0以上の数値が必要です")
    if spec.limit is not None and not spec.limit.test(value):
        raise EntryError(spec.limit.message)
    return int(value) if spec.precision.digits == 0 else value


def enter(spec: Field, text: str) -> Any:
    """The JSON value of *text* in this field; EntryError when it cannot be entered."""
    text = _normalized(text)
    if not text:
        return None
    if spec.kind == "blank":
        raise EntryError(spec.message)
    if spec.kind == "number":
        return _number(spec, text)
    if spec.kind == "integer":
        if not _INTEGER.fullmatch(text):
            raise EntryError("整数を入力してください")
        value = int(text)
        if not spec.minimum <= value <= spec.maximum:
            raise EntryError(f"{spec.minimum}～{spec.maximum}の整数が必要です")
        return value
    if spec.kind == "choice" and text not in spec.choices:
        raise EntryError("".join(f"「{option}」" for option in spec.choices) + "のいずれかを選んでください")
    return text


def display(spec: Field, value: Any) -> str:
    """The cell text of a saved value: a number with its printed digits, anything else as it is."""
    if value is None:
        return ""
    if spec.kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
        assert spec.precision is not None
        digits = spec.precision.digits
        if math.isfinite(value) and round_half_away(value, digits) == value:
            return f"{value:.{digits}f}"
    return str(value)


def problem(spec: Field, value: Any) -> str | None:
    """Why a saved value is not a valid input of this field (a needed blank included), or None."""
    try:
        spec.read(Reader(value, ""))
    except InputError as exc:
        return str(exc).removeprefix(": ")
    return None
