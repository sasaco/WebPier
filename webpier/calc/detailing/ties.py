"""中間帯鉄筋 (CONTEXT.md 帯鉄筋の方向別有効本数・中間帯鉄筋, decision 73): where the hoop legs that resist the
shear of one direction of the column stand.

The legs of the 帯鉄筋の方向別有効本数 n of a direction run across the section in that direction and stand side by side
along the faces of that direction's main bars: for 線路 along the faces normal to Y (a leg at an x, the face W6 long),
for 直角 along the faces normal to X (a leg at a y, the face B6 long), in the coordinates of calc.column_rebar (mm,
origin at the upper-left corner).

- Two legs are the outer hoop's (外巻き帯鉄筋): at the outermost bars of the section along the face (the bars the
  hoop encloses, of either direction).
- The other n − 2 are 中間帯鉄筋. The k-th (k = 1 … n − 2) hooks the layer-1 bar of the direction's main bars nearest
  to the point k·span／(n − 1) that divides the face into n − 1 equal parts (of two equally near, the one nearer the
  origin). The point is printed to 0.1 mm and compared as printed (ADR-0003).
- Sets (組): n／2 in all, the outer hoop 1, the intermediate ties (n − 2)／2 (a set is two legs).
- The lateral spacing of the 48φ check is the largest gap between neighbouring legs, the outer legs included.

Each leg stands at the centre of the bar it holds, as the bars are in use (with the changes of the 方向別の鉄筋配置表).
The hoops are the row of the direction that contains the column base (start blank or 0), as the column check
(calc.column_check) reads them. A layout that cannot hold the ties is an input error naming its path: fewer than two
legs, no layer-1 bars for an intermediate tie, or two legs on one bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.errors import InputError
from ...core.printed import Precision, Printed
from ...inputs import PierInput, choices
from ...inputs.rebar import LENGTH_MM
from .._exact import d, put
from ..column_rebar import ColumnLayout, column_layout

SETS = Precision(1, "組")  # 1.0 組, 4.0 組 (the sample 0400 6))
_COLUMN = "鉄筋.柱"
_ROWS = f"{_COLUMN}.column_hoops.direction_rows"


@dataclass(frozen=True)
class BaseHoops:
    """The hoop row of a direction that contains the column base."""

    direction: str  # choices.REBAR_DIRECTIONS
    path: str  # the input path of the row, for the messages
    diameter: Printed  # mm
    legs: int  # 帯鉄筋の方向別有効本数 n
    pitch: Printed  # mm, along the column
    grade: str  # the column's transverse steel


@dataclass(frozen=True)
class TieLayout:
    """The legs of the hoops of one direction along the face (mm)."""

    direction: str  # choices.REBAR_DIRECTIONS
    effective_legs: int  # n
    span: Printed  # the face: W6 for 線路, B6 for 直角
    targets: tuple[Printed, ...]  # k·span／(n − 1), k = 1 … n − 2
    outer: tuple[Printed, Printed]  # the outer hoop's legs
    intermediate: tuple[Printed, ...]  # the intermediate ties' legs, ascending, one per target
    sets: Printed  # n／2
    intermediate_sets: Printed  # (n − 2)／2
    max_spacing: Printed  # the largest gap between neighbouring legs

    @property
    def legs(self) -> tuple[Printed, ...]:
        """Every leg, ascending."""
        return (self.outer[0], *self.intermediate, self.outer[1])


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def base_hoops(pier: PierInput, direction: str) -> BaseHoops:
    """The hoop row of *direction* that contains the column base: exactly one is needed."""
    column = pier.rebar.column
    rows = [(index, row) for index, row in enumerate(column.hoops.rows)
            if row.direction == direction and (row.start is None or row.start.value == 0)]
    if len(rows) != 1:
        raise InputError(f"{_ROWS}: {direction}の帯鉄筋で柱下端を含む行がちょうど1行必要です（{len(rows)}行）")
    ((index, row),) = rows
    here = f"{_ROWS}[{index}]"
    return BaseHoops(direction=direction, path=here, diameter=_need(row.diameter, f"{here}.diameter_mm"),
                     legs=_need(row.effective_legs, f"{here}.effective_legs"),
                     pitch=_need(row.pitch, f"{here}.pitch_mm"),
                     grade=_need(column.materials.transverse, f"{_COLUMN}.materials.transverse"))


def _along(direction: str):
    """The coordinate of a bar along the faces of *direction*."""
    return (lambda bar: bar.x) if direction == choices.REBAR_DIRECTIONS[0] else (lambda bar: bar.y)


def tie_layout(layout: ColumnLayout, direction: str, legs: int, path: str) -> TieLayout:
    """The legs of *legs* effective hoops of *direction* in *layout*; *path* names the hoop row in the messages."""
    if legs < 2:
        raise InputError(f"{path}.effective_legs: 外巻き帯鉄筋の2本を含めて2本以上が必要です（{legs}本）")
    along = _along(direction)
    span = layout.width if direction == choices.REBAR_DIRECTIONS[0] else layout.height
    positions = sorted({along(bar).value: along(bar) for bar in layout.bars}.items())
    outer = (positions[0][1], positions[-1][1])
    first = sorted({along(bar).value: along(bar) for bar in layout.bars
                    if (direction, 1) in bar.rows}.items())
    if legs > 2 and not first:
        raise InputError(f"{path}.effective_legs: 中間帯鉄筋を掛ける{direction}の1段目の主鉄筋がありません")
    targets = tuple(put(LENGTH_MM, d(span) * k / (legs - 1)) for k in range(1, legs - 1))
    intermediate = []
    for target in targets:
        _, bar = min(first, key=lambda item: (abs(d(item[1]) - d(target)), item[0]))
        intermediate.append(bar)
    every = (outer[0], *intermediate, outer[1])
    values = [leg.value for leg in every]
    if len(set(values)) != len(values):
        raise InputError(f"{path}.effective_legs: 中間帯鉄筋を掛ける{direction}の1段目の主鉄筋が足りません"
                         f"（有効本数 {legs}本で、同じ鉄筋に2本の脚が掛かります）")
    gaps = [d(b) - d(a) for a, b in zip(every, every[1:])]
    return TieLayout(direction=direction, effective_legs=legs, span=span, targets=targets, outer=outer,
                     intermediate=tuple(intermediate), sets=put(SETS, Decimal(legs) / 2),
                     intermediate_sets=put(SETS, Decimal(legs - 2) / 2), max_spacing=put(LENGTH_MM, max(gaps)))


def column_ties(pier: PierInput, direction: str) -> TieLayout:
    """The legs of the hoops of *direction* at the column base (the row that contains it)."""
    hoops = base_hoops(pier, direction)
    return tie_layout(column_layout(pier), direction, hoops.legs, hoops.path)
