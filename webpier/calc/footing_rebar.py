"""フーチングの配筋 (decision 60): what the footing section check (0810 / 0820) and the response values (0800) are
given from 鉄筋.フーチング.

Each direction (LONGITUDINAL 線路, TRANSVERSE 直角) reads its one lower main row, the tensile bars of the overhang
(1 m 当たり 1000／pitch 本; the centre of the bars from the lower face is center_mm when the cover is 指定, else
pure_cover_mm plus the diameters of the lower rows stacked outside it (stack_order 1 is outermost) plus half its own
diameter), and its one stirrup row (the legs per metre across the width: the density, or 1000／width_pitch_mm by
spacing). The upper rows are not read (the sample 12_フーチング.pdf 255 has no compression bars). The grade of a row
is its own, else the member's; f'ck is the footing concrete's (鉄筋.フーチング.concrete_strength_mpa). Anything
blank, a pitch or spacing that does not divide 1 m, a density that is not whole, two layers or more, or a direction
without exactly one lower main row or one stirrup row is an input error naming its path. The check itself is
Capacita's (ADR-0008).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput, choices
from ..inputs.rebar import FootingBars, FootingMainRow
from ._exact import d, put

_FOOTING = "鉄筋.フーチング"
LONGITUDINAL, TRANSVERSE = choices.REBAR_DIRECTIONS
_LOWER = choices.BEAM_FACES[1]
LENGTH_MM = Precision(1, "mm")
_METRE_MM = Decimal(1000)  # the bars are counted per 1 m of width (sample 12-255: D25@125 → D25-8本)


@dataclass(frozen=True)
class MainBars:
    """The lower (tensile) bars of the overhang in one direction, per 1 m of width."""

    diameter: Printed  # mm, nominal (D25 → 25)
    count: int  # per 1 m
    pitch: Printed  # mm
    cover: Printed  # mm, the centre of the bars from the lower face
    grade: str


@dataclass(frozen=True)
class Stirrups:
    """The shear reinforcement of the overhang in one direction, per 1 m of width."""

    diameter: Printed  # mm
    legs: int  # per 1 m of width
    pitch: Printed  # mm, along the overhang
    grade: str


@dataclass(frozen=True)
class FootingReinforcement:
    direction: str  # LONGITUDINAL or TRANSVERSE
    main: MainBars
    stirrups: Stirrups
    fck: Printed  # N/mm2


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _per_metre(spacing: Printed, path: str) -> int:
    bars = _METRE_MM / d(spacing)
    if bars != bars.to_integral_value():
        raise InputError(f"{path}: 1 m 当たりの本数が整数になりません（1000／{spacing.value}）")
    return int(bars)


def _one(rows: list, path: str, what: str):
    if len(rows) != 1:
        raise InputError(f"{path}: {what}の行がちょうど1行必要です（{len(rows)}行）")
    return rows[0]


def _cover(footing: FootingBars, index: int, row: FootingMainRow, here: str) -> Printed:
    mode = _need(row.cover_mode, f"{here}.cover_mode")
    if mode == choices.COVER_SPECIFIED:
        return _need(row.center, f"{here}.center_mm")
    pure = _need(footing.pure_cover, f"{_FOOTING}.pure_cover_mm")
    order = _need(row.stack_order, f"{here}.stack_order")
    outside = Decimal(0)
    for other_index, other in enumerate(footing.main_rows):
        if other_index == index or other.face != _LOWER:
            continue
        other_order = _need(other.stack_order, f"{_FOOTING}.main_rows[{other_index}].stack_order")
        if other_order == order:
            raise InputError(f"{_FOOTING}.main_rows: 下側の主鉄筋の重ね順 {order} が2行にあります")
        if other_order < order:
            outside += d(_need(other.diameter, f"{_FOOTING}.main_rows[{other_index}].diameter_mm"))
    return put(LENGTH_MM, d(pure) + outside + d(_need(row.diameter, f"{here}.diameter_mm")) / 2)


def _main(footing: FootingBars, direction: str) -> MainBars:
    path = f"{_FOOTING}.main_rows"
    rows = [(index, row) for index, row in enumerate(footing.main_rows)
            if row.direction == direction and row.face == _LOWER]
    index, row = _one(rows, path, f"{direction}方向の下側の主鉄筋")
    here = f"{path}[{index}]"
    diameter = _need(row.diameter, f"{here}.diameter_mm")
    pitch = _need(row.pitch, f"{here}.pitch_mm")
    count = _per_metre(pitch, f"{here}.pitch_mm")
    if _need(row.layers, f"{here}.layers") != 1:
        raise InputError(f"{here}.layers: 2段以上は表せません")
    cover = _cover(footing, index, row, here)
    grade = row.material or footing.materials.main
    if grade is None:
        raise InputError(f"{here}.material: 値が必要です（行と{_FOOTING}.materials.main が空欄）")
    return MainBars(diameter=diameter, count=count, pitch=pitch, cover=cover, grade=grade)


def _stirrups(footing: FootingBars, direction: str) -> Stirrups:
    path = f"{_FOOTING}.band_rows"
    rows = [(index, row) for index, row in enumerate(footing.band_rows) if row.direction == direction]
    index, row = _one(rows, path, f"{direction}方向のスターラップ")
    here = f"{path}[{index}]"
    diameter = _need(row.diameter, f"{here}.diameter_mm")
    pitch = _need(row.pitch, f"{here}.pitch_mm")
    mode = _need(row.width_mode, f"{here}.distribution_mode")
    if mode == choices.WIDTH_DENSITY:
        density = _need(row.density, f"{here}.density_per_m")
        if d(density) != d(density).to_integral_value():
            raise InputError(f"{here}.density_per_m: 1 m 当たりの本数が整数になりません（{density.value}）")
        legs = int(d(density))
    else:
        legs = _per_metre(_need(row.width_pitch, f"{here}.width_pitch_mm"), f"{here}.width_pitch_mm")
    grade = row.material or footing.materials.transverse
    if grade is None:
        raise InputError(f"{here}.material: 値が必要です（行と{_FOOTING}.materials.transverse が空欄）")
    return Stirrups(diameter=diameter, legs=legs, pitch=pitch, grade=grade)


def footing_reinforcement(pier: PierInput, direction: str) -> FootingReinforcement:
    """The bars of the overhang in *direction* (LONGITUDINAL or TRANSVERSE) as the section check is given them."""
    footing = pier.rebar.footing
    return FootingReinforcement(direction=direction, main=_main(footing, direction),
                                stirrups=_stirrups(footing, direction), fck=pier.materials.footing)
