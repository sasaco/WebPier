"""Calculated workbook cells and compatibility defaults for bearing positions.

These definitions are application code, not additional input-schema fields.
The caller supplies validated source numbers, allowing the editor to evaluate
pending cell text without changing its document and the parsers to share them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, localcontext
import math
from typing import Any


InputPath = tuple[str | int, ...]
NumberGetter = Callable[[InputPath], float | None]


class FormulaError(ValueError):
    """A calculated cell has an invalid or non-finite result."""


def _zero(value: float | None) -> float:
    return 0.0 if value is None else value


@dataclass(frozen=True)
class InputFormula:
    path: InputPath
    dependencies: tuple[InputPath, ...]
    expression: str
    _calculate: Callable[[tuple[float | None, ...]], float]

    def evaluate(self, getter: NumberGetter) -> float:
        # Read/validate dependencies outside the arithmetic handler so a source
        # error retains its own path rather than being blamed on the result.
        values = tuple(getter(path) for path in self.dependencies)
        label = ".".join(map(str, self.path))
        try:
            result = float(self._calculate(values))
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise FormulaError(f"{label}: 数式を計算できません") from exc
        if not math.isfinite(result):
            raise FormulaError(f"{label}: 数式の計算結果が有限の数値ではありません")
        return result


B9_PATH: InputPath = ("下部構造", "寸法", "側面", "B9")
SURFACE_THICKNESS_PATH: InputPath = ("地盤データ", "層", 0, "層厚")
DISPLACED_SOIL_PATH: InputPath = ("下部構造", "単位体積重量", "土", "排除した土")
SUPPORT_POSITION_PATHS = tuple(("上部構造", side, "支承位置_f") for side in ("起点側", "終点側"))
SUPPORT_LENGTH_PATHS = (("上部構造", "起点側", "桁長", "L2"),
                        ("上部構造", "終点側", "桁長", "L1"))


def opposite_support_position(l2_origin: float, l1_end: float, position: float) -> float:
    # Decimal arithmetic avoids displaying 0.5499999999999999 for .575+.375-.4.
    # The generous precision also preserves cancellation across finite doubles.
    with localcontext() as context:
        context.prec = 1000
        result = float(Decimal(str(l2_origin)) + Decimal(str(l1_end)) - Decimal(str(position)))
    if not math.isfinite(result):
        raise FormulaError("反対側の支承位置 f の計算結果が有限の数値ではありません")
    return result


def support_position_value(getter: Callable[[InputPath], Any], side: str) -> float:
    """Keep explicit f; default only absent/null f, without hiding bad input."""
    index = 0 if side == "起点側" else 1

    def number(path: InputPath) -> float:
        value = getter(path)
        label = ".".join(map(str, path))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FormulaError(f"{label}: 有限の数値が必要です")
        try:
            result = float(value)
        except (OverflowError, ValueError) as exc:
            raise FormulaError(f"{label}: 有限の数値が必要です") from exc
        if not math.isfinite(result):
            raise FormulaError(f"{label}: 有限の数値が必要です")
        return result

    own, other = SUPPORT_POSITION_PATHS[index], SUPPORT_POSITION_PATHS[1 - index]
    if getter(own) is not None:
        return number(own)
    if getter(other) is None:
        return number(SUPPORT_LENGTH_PATHS[index])
    return opposite_support_position(number(SUPPORT_LENGTH_PATHS[0]), number(SUPPORT_LENGTH_PATHS[1]), number(other))


def _surface(values: tuple[float | None, ...]) -> float:
    h6, h5, df1, df2 = values
    # Excel MIN(range) ignores empty cells, but includes numeric zero.
    covers = [value for value in (df1, df2) if value is not None]
    return _zero(h6) + _zero(h5) + min(covers, default=0.0)


def _formulas() -> tuple[InputFormula, ...]:
    formulas = [
        InputFormula(B9_PATH, (("下部構造", "寸法", "側面", "B7"),),
                     "B7", lambda v: _zero(v[0])),
        InputFormula(SURFACE_THICKNESS_PATH, (
            ("下部構造", "寸法", "高さ", "H6"),
            ("下部構造", "寸法", "高さ", "H5"),
            ("下部構造", "土かぶり", "起点側_df1"),
            ("下部構造", "土かぶり", "終点側_df2"),
        ), "H6+H5+MIN(df1,df2)", _surface),
        InputFormula(DISPLACED_SOIL_PATH, (("地盤データ", "層", 0, "単位体積重量", "湿潤"),),
                     "先頭地層の湿潤単位体積重量", lambda v: _zero(v[0])),
    ]
    return tuple(formulas)


INPUT_FORMULAS = _formulas()
FORMULAS_BY_PATH = {formula.path: formula for formula in INPUT_FORMULAS}
