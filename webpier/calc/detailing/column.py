"""4.2 躯体の構造細目: the detailing of the column (decision 73, ADR-0012; the sample 0400 2.1).

The bars are the column layout (calc.column_rebar) in use; each direction is the bending direction of the column
check (calc.column_check: 線路 b = W6, h = B6; 直角 b = B6, h = W6).

- 1) (a) and 3), once for the whole section: As is every bar, grouped by the bars of the main rows of 線路 (the
  sample's 引張・圧縮鉄筋, with the corner bars they share) and the others (側方鉄筋), each by size; Pc = As／(W6·B6).
- 5) 鉄筋のあき of the direction's main bars (any bar of its rows): the least centre spacing of neighbouring bars on
  one line of the face and of neighbouring layers on one side, less the largest bar of the rows; the limits are a
  column's (40 mm, 1.5φ, 4/3 Dmax with the column's Dmax).
- 6), 8), 9): the hoops of the direction at the column base (calc.detailing.ties.base_hoops): Ps = pw = n·Aw／(b·s).
- 7) ① 一般部 and ② 塑性ヒンジ部 against the pitch of those hoops, with d = h − the centroid of the direction's main
  rows (as generated, one side), φ of the main bars the smallest of them, the short side min(W6, B6); ③ the largest
  gap of the legs (calc.detailing.ties) against 48φ of the hoops.

The checks that use section forces (Mcrd, 0.008Ac, the maximum reinforcement, σc) are Capacita's (ADR-0012) and have
no value here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.errors import InputError
from ...core.printed import Printed
from ...inputs import PierInput, choices
from .._exact import d, put
from ..column_check import LONGITUDINAL, TRANSVERSE
from ..column_rebar import ColumnLayout, column_layout
from .common import (LENGTH, BarGroup, CapacityRatio, ClearSpacing, DuctilityLimit, ShearRatio, SteelRatio,
                     StirrupSpacing, bound, capacity_ratio, clear_spacing, confinement_spacing, count,
                     ductility_limit, general_spacing, least_gap, need, shear_ratio, steel_ratio)
from .ties import BaseHoops, TieLayout, base_hoops, tie_layout

_MAIN = "鉄筋.柱.main_bars"
LATERAL_FACTOR = 48  # ③ 帯鉄筋の横方向の間隔 ≦ 48φ (RC標準第Ⅲ編 2.3.5.4; the sample 0400 7) ②)


@dataclass(frozen=True)
class LateralSpacing:
    """7) ③: the largest gap of neighbouring legs ≦ 48φ of the hoops."""

    ties: TieLayout
    limit: Printed  # 48φ, mm
    ok: bool


@dataclass(frozen=True)
class ColumnDirection:
    direction: str  # choices.REBAR_DIRECTIONS
    width: Printed  # b, mm
    depth: Printed  # h, mm
    effective_depth: Printed  # d, mm
    main_diameter: Printed  # φ of the main bars of the direction (the smallest)
    spacing: ClearSpacing  # 5)
    hoops: BaseHoops
    shear: ShearRatio  # 6)
    general: StirrupSpacing  # 7) ①
    confinement: StirrupSpacing  # 7) ②
    lateral: LateralSpacing  # 7) ③
    ductility: DuctilityLimit  # 8)
    capacity: CapacityRatio  # 9)

    @property
    def ok(self) -> bool:
        return all((self.spacing.ok, self.shear.ok, self.general.ok, self.confinement.ok, self.lateral.ok,
                    self.ductility.ok))


@dataclass(frozen=True)
class ColumnDetailing:
    amount: SteelRatio  # 1) (a), 3): the main bars of 線路, then the others
    main_count: int  # how many groups of amount are the main bars of 線路
    fck: Printed  # N/mm2
    aggregate_max: Printed  # Dmax, mm
    directions: tuple[ColumnDirection, ...]  # 線路, 直角

    @property
    def ok(self) -> bool:
        return self.amount.minimum_ok and self.amount.maximum_ok and all(item.ok for item in self.directions)


def _groups(bars) -> list[BarGroup]:
    sizes: dict[float, tuple[Printed, int]] = {}
    for bar in bars:
        diameter, number = sizes.get(bar.diameter.value, (bar.diameter, 0))
        sizes[bar.diameter.value] = (diameter, number + 1)
    return [BarGroup.of(diameter, count(number), _MAIN) for _, (diameter, number) in sorted(sizes.items())]


def _of(direction: str, bar) -> bool:
    return any(key[0] == direction for key in bar.rows)


def _spacing(layout: ColumnLayout, direction: str, aggregate_max: Printed) -> tuple[ClearSpacing, Printed]:
    """5) and the smallest main bar of *direction*."""
    rail = direction == choices.REBAR_DIRECTIONS[0]
    depth = layout.height if rail else layout.width
    bars = [bar for bar in layout.bars if _of(direction, bar)]
    lines: dict[float, list[Printed]] = {}
    for bar in bars:
        fixed, along = (bar.y, bar.x) if rail else (bar.x, bar.y)
        lines.setdefault(fixed.value, []).append(along)
    fixed = sorted({(bar.y if rail else bar.x).value: bar.y if rail else bar.x for bar in bars}.values(), key=d)
    sides = ([item for item in fixed if 2 * d(item) < d(depth)], [item for item in fixed if 2 * d(item) > d(depth)])
    largest = max((bar.diameter for bar in bars), key=d)
    smallest = min((bar.diameter for bar in bars), key=d)
    return clear_spacing(least_gap(lines.values()), least_gap(sides), largest, aggregate_max, column=True), smallest


def _effective_depth(layout: ColumnLayout, direction: str, depth: Printed) -> Printed:
    rows = [row for row in layout.rows if row.direction == direction]
    total = sum(len(row.positions) for row in rows)
    centroid = sum((d(row.center) * len(row.positions) for row in rows), Decimal(0)) / total
    return put(LENGTH, d(depth) - centroid)


def _direction(pier: PierInput, layout: ColumnLayout, direction: str, aggregate_max: Printed) -> ColumnDirection:
    bending = LONGITUDINAL if direction == LONGITUDINAL.face else TRANSVERSE
    width, depth = bending.section(layout)
    if not any(row.direction == direction for row in layout.rows):
        raise InputError(f"{_MAIN}.{direction}: {direction}の主鉄筋が必要です")
    spacing, main = _spacing(layout, direction, aggregate_max)
    effective = _effective_depth(layout, direction, depth)
    hoops = base_hoops(pier, direction)
    shear = shear_ratio(hoops.diameter, count(hoops.legs), width, hoops.pitch, f"{hoops.path}.diameter_mm")
    ties = tie_layout(layout, direction, hoops.legs, hoops.path)
    lateral = bound("stirrup_48", hoops.diameter, LATERAL_FACTOR).value
    short = min(layout.width, layout.height, key=d)
    return ColumnDirection(
        direction=direction, width=width, depth=depth, effective_depth=effective, main_diameter=main,
        spacing=spacing, hoops=hoops, shear=shear,
        general=general_spacing(effective, main, hoops.diameter, hoops.pitch),
        confinement=confinement_spacing(effective, main, hoops.diameter, short, hoops.pitch),
        lateral=LateralSpacing(ties, lateral, d(ties.max_spacing) <= d(lateral)),
        ductility=ductility_limit(hoops.grade, shear.ratio, "鉄筋.柱.materials.transverse"),
        capacity=capacity_ratio(shear.ratio, hoops.grade, pier.materials.column))


def column_detailing(pier: PierInput) -> ColumnDetailing:
    layout = column_layout(pier)
    aggregate_max = need(pier.rebar.column.aggregate_max, "鉄筋.柱.aggregate_max_mm")
    rail = choices.REBAR_DIRECTIONS[0]
    main = _groups(bar for bar in layout.bars if _of(rail, bar))
    side = _groups(bar for bar in layout.bars if not _of(rail, bar))
    grade = need(pier.rebar.column.materials.main, "鉄筋.柱.materials.main")
    return ColumnDetailing(amount=steel_ratio((*main, *side), grade, layout.width, layout.height),
                           main_count=len(main),
                           fck=pier.materials.column, aggregate_max=aggregate_max,
                           directions=tuple(_direction(pier, layout, direction, aggregate_max)
                                            for direction in choices.REBAR_DIRECTIONS))
