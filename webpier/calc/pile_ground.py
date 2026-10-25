"""The values WebPier gives SOIL-JR for the ground of a pile foundation (0500 杭基礎, ADR-0013, decision 85).

SOIL-JR 5.2-L03 models the ground of a pile foundation (its springs and the design limits of the pile head) from an
input file (.sdt, written by export.soiljr). Its rows are not the ground sheet of the input: this module derives them.

* **The ground above the pile head** (the 上載土 row of the .sdt, from the ground surface to the bottom of the footing,
  Df = H6 + H5 + min(df1, df2)) is one row whose wet and submerged unit weights are the thickness-weighted means of the
  layers it cuts, above and below the water, so that the earth pressure at the footing base is the one the layers give.
* **The ground along the pile** (from the footing base to the pile tip, the pile length below it) is the layers cut at
  those two depths; the last layer goes on below the last thickness. A cut keeps the layer's soil, values and De. The
  strength and deformation are design values: Ex = Ed and ρgE = γgE = 1 (SOIL-JR then takes Ed as it is).
* **The pile** is the section of its type (the area and the second moment of area as SOIL-JR calculates them), and
  **the layout** is the rows SOIL-JR takes: the number of piles in each column and its distance from the first one.

Every length is calculated in whole millimetres, so a cut layer's thickness is exact and the thicknesses add up to the
pile length. Nothing is filled in: a value a row needs is an input error naming its path (the sheet's blanks are
allowed until a stage asks for them).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import LENGTH, UNIT_WEIGHT, Precision, Printed
from ..inputs import PierInput, choices
from ..inputs.fields import FRICTION_ANGLE, STRESS
from ._exact import d, put
from .materials import concrete

SECTION_AREA = Precision(6, "m2")
SECOND_MOMENT = Precision(6, "m4")
MODULUS = Precision(1, "kN/mm2")
THICKNESS = Precision(1, "mm")
PI = Decimal("3.1415926536")  # the constant of SOIL-JR's formulas
STEEL_MODULUS = Printed(200.0, 1, "kN/mm2")  # Es of the steel pipe, a constant of SOIL-JR
MAX_LAYERS = 20  # SOIL-JR takes up to 20 layers below the pile head
SOIL_KINDS = {"砂質土": 1, "粘性土": 2, "砂礫": 3}  # SOIL-JR's J_KIND
STRATIFIED = "砂質土と粘性土の互層"
_MM = Decimal(1000)
_LAYERS = "地盤データ.層"


@dataclass(frozen=True)
class SoilRow:
    """A layer row of the .sdt: the part of a layer along the pile."""

    layer: int  # the index in 地盤データ.層
    name: str
    thickness: Printed  # m
    kind: int  # J_KIND: 1 砂質土, 2 粘性土, 3 砂礫
    soil_type: str
    n_value: Printed
    cohesion: Printed  # c, kN/m2 (0 for a sand without one)
    friction_angle: Printed  # φd, ° (0 for a clay without one)
    unit_weight_wet: Printed
    unit_weight_submerged: Printed
    deformation_modulus: Printed  # Ed = Ex, kN/m2
    reduction: Printed | None  # De of the layer in liquefaction; None is blank, 1


@dataclass(frozen=True)
class HeadGround:
    """The 上載土 row: the ground above the pile head."""

    thickness: Printed  # Df, m
    unit_weight_wet: Printed  # weighted over the layers above the water
    unit_weight_submerged: Printed  # weighted over the layers below it
    layers: tuple[int, ...]  # the indexes in 地盤データ.層 it is made of


@dataclass(frozen=True)
class PileSection:
    """The pile of the type, as SOIL-JR's K_KIND, K_KOHO and the dimensions of its second line take it."""

    kind: int  # K_KIND: 1 鉄筋コンクリート杭, 5 鋼管杭
    method: int  # K_KOHO: 1 場所打ち杭, 7 鋼管ソイルセメント杭
    construction: int  # K_SJYOUKEN: 1 自然泥水, 2 安定液使用, 0 none
    diameter: Printed  # D1: the pile diameter, or the soil cement diameter
    inner_diameter: Printed | None  # D2: the steel pipe diameter of a 鋼管ソイルセメント杭
    thickness: Printed | None  # t1, mm
    corrosion: Printed | None  # mm
    es: Printed | None  # kN/mm2
    ec: Printed | None  # kN/mm2
    area: Printed  # A, m2
    second_moment: Printed  # I, m4
    unit_weight: Printed  # K_Ganma, kN/m3
    minimum_embedment: Printed  # K_NEIRE, the least depth into the supporting layer


@dataclass(frozen=True)
class PileColumn:
    """One column of piles of a direction: the piles it has left and its distance from the first column."""

    count: int
    distance: Printed  # m


@dataclass(frozen=True)
class PileRows:
    """The layout as SOIL-JR takes it. ``along`` is its 橋軸方向 (the line), ``across`` its 直角方向."""

    pattern: int  # K_HAITI: 1 格子, 2 千鳥
    along: tuple[PileColumn, ...]
    across: tuple[PileColumn, ...]
    spacing_along: Printed  # K_M_KANKAKU, the first interval (0 for one column)
    spacing_across: Printed  # K_N_KANKAKU
    lm: tuple[Printed, Printed]  # K_LM
    ln: tuple[Printed, Printed]  # K_LN
    rows_written: bool  # K_FLG: the rows are kept as written (holes, unequal intervals)
    removed: tuple[tuple[int, int], ...]  # (column across, column along) as SOIL-JR's IDEL, JDEL
    piles: int  # the number of piles


@dataclass(frozen=True)
class PileGroundResult:
    foundation: str
    depth: Printed  # Df
    length: Printed  # L, the pile length below the footing base
    water_depth: Printed  # K_SUII: the normal water level below the ground surface
    head: HeadGround
    layers: tuple[SoilRow, ...]
    section: PileSection
    rows: PileRows
    liquefaction: bool  # some layer along the pile has a De below 1


def _mm(value: Printed) -> int:
    return int(d(value) * _MM)


def _length(millimetres: int) -> Printed:
    return LENGTH(float(Decimal(millimetres) / _MM))


def _required(value: Printed | None, path: str) -> Printed:
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _positive(value: Printed | None, path: str) -> Printed:
    value = _required(value, path)
    if value.value <= 0:
        raise InputError(f"{path}: 0より大きい値が必要です（SOIL-JR の入力）")
    return value


def _bounds(pier: PierInput) -> list[tuple[int, int | None]]:
    """The top and the bottom of each layer below the ground surface, in mm; the last layer has no bottom."""
    layers = pier.soil.layers
    bounds: list[tuple[int, int | None]] = []
    top = 0
    for index, layer in enumerate(layers):
        if index == len(layers) - 1:
            bounds.append((top, None))
        else:
            thickness = _required(layer.thickness, f"{_LAYERS}[{index}].層厚")
            if thickness.value <= 0:
                raise InputError(f"{_LAYERS}[{index}].層厚: 正の数値が必要です（最後の層は下に続くので空欄でよい）")
            bottom = top + _mm(thickness)
            bounds.append((top, bottom))
            top = bottom
    return bounds


def _head(pier: PierInput, bounds: list[tuple[int, int | None]], depth: int, water: int) -> HeadGround:
    """The 上載土 row: layers cut at the footing base, weighted above and below the water at *water* mm."""
    wet = [Decimal(0), Decimal(0)]  # thickness, thickness × γ
    submerged = [Decimal(0), Decimal(0)]
    used: list[int] = []
    for index, (top, bottom) in enumerate(bounds):
        end = depth if bottom is None else min(bottom, depth)
        if top >= end:
            continue
        layer = pier.soil.layers[index]
        used.append(index)
        path = f"{_LAYERS}[{index}].単位体積重量"
        gamma_wet = d(_positive(layer.unit_weight_wet, f"{path}.湿潤"))
        gamma_submerged = d(_positive(layer.unit_weight_submerged, f"{path}.水中"))
        above = max(0, min(end, water) - top)  # the part above the water
        below = (end - top) - above
        wet[0] += Decimal(above)
        wet[1] += Decimal(above) * gamma_wet
        submerged[0] += Decimal(below)
        submerged[1] += Decimal(below) * gamma_submerged
    first, last = pier.soil.layers[used[0]], pier.soil.layers[used[-1]]  # a part with none has its neighbour's weight
    unit_wet = wet[1] / wet[0] if wet[0] else d(first.unit_weight_wet)
    unit_submerged = submerged[1] / submerged[0] if submerged[0] else d(last.unit_weight_submerged)
    return HeadGround(thickness=_length(depth), unit_weight_wet=put(UNIT_WEIGHT, unit_wet),
                      unit_weight_submerged=put(UNIT_WEIGHT, unit_submerged), layers=tuple(used))


def _soil_row(pier: PierInput, index: int, thickness: int) -> SoilRow:
    layer = pier.soil.layers[index]
    path = f"{_LAYERS}[{index}]"
    if layer.soil_type == STRATIFIED:
        raise InputError(f"{path}.土質区分: SOIL-JR の地盤種別は砂質土・粘性土・砂礫だけです"
                         f"（{STRATIFIED}は杭の区間の層にできません。どれかに分けてください）")
    clay = layer.soil_type == "粘性土"
    friction_angle = layer.friction_angle
    cohesion = layer.cohesion
    if clay:
        cohesion = _positive(cohesion, f"{path}.粘着力_c")
        friction_angle = FRICTION_ANGLE(0) if friction_angle is None else friction_angle
    else:
        friction_angle = _positive(friction_angle, f"{path}.内部摩擦角_φd")
        cohesion = STRESS(0) if cohesion is None else cohesion
    n_value = _positive(layer.n_value, f"{path}.N値")  # a whole number: the input prints it with no decimal
    return SoilRow(
        layer=index, name=layer.name, thickness=_length(thickness), kind=SOIL_KINDS[layer.soil_type],
        soil_type=layer.soil_type, n_value=n_value, cohesion=cohesion, friction_angle=friction_angle,
        unit_weight_wet=_positive(layer.unit_weight_wet, f"{path}.単位体積重量.湿潤"),
        unit_weight_submerged=_positive(layer.unit_weight_submerged, f"{path}.単位体積重量.水中"),
        deformation_modulus=_positive(layer.deformation_modulus, f"{path}.変形係数_Ed"),
        reduction=layer.reduction)


def _along_pile(pier: PierInput, bounds: list[tuple[int, int | None]], depth: int, length: int
                ) -> tuple[SoilRow, ...]:
    """The layers cut at the pile head and the pile tip, from the top; the thicknesses add up to the length."""
    tip = depth + length
    rows = []
    for index, (top, bottom) in enumerate(bounds):
        start, end = max(top, depth), tip if bottom is None else min(bottom, tip)
        if end > start:
            rows.append(_soil_row(pier, index, end - start))
    if len(rows) > MAX_LAYERS:
        raise InputError(f"{_LAYERS}: 杭の区間の層が{len(rows)}層あります（SOIL-JR は{MAX_LAYERS}層まで）")
    return tuple(rows)


def _ec(pier: PierInput) -> Printed:
    """Ec of the pile concrete in kN/mm2 (decision 25's table), 1 decimal: the printed mantissa × 10 (10^7 kN/m2)."""
    cast = pier.piles.cast_in_place
    return MODULUS(float(d(concrete(cast.fck, "杭基礎.場所打ち杭.f'ck").modulus) * 10))


def _area(diameter: Decimal) -> Printed:
    return put(SECTION_AREA, PI * diameter * diameter / 4)


def _section(pier: PierInput, rows: tuple[SoilRow, ...]) -> PileSection:
    piles = pier.piles
    unit_weight = piles.unit_weight
    # the least depth into the supporting layer: D1, half of it when the layer at the tip is a clay below others
    half = len(rows) > 1 and rows[-1].kind == 2
    if pier.substructure.foundation == choices.CAST_IN_PLACE_PILE:
        cast = piles.cast_in_place
        diameter = cast.diameter
        return PileSection(
            kind=1, method=1, construction=choices.CAST_IN_PLACE_CONDITIONS.index(cast.condition) + 1,
            diameter=diameter, inner_diameter=None, thickness=None, corrosion=None, es=None, ec=_ec(pier),
            area=_area(d(diameter)), second_moment=put(SECOND_MOMENT, PI * d(diameter) ** 4 / 64),
            unit_weight=unit_weight, minimum_embedment=put(LENGTH, d(diameter) / (2 if half else 1)))
    steel = piles.steel_soil_cement
    outer, wall, corrosion = d(steel.steel_diameter), d(steel.thickness) / _MM, d(steel.corrosion) / _MM
    return PileSection(
        kind=5, method=7, construction=0, diameter=steel.soil_cement_diameter, inner_diameter=steel.steel_diameter,
        thickness=steel.thickness, corrosion=steel.corrosion, es=STEEL_MODULUS, ec=None,
        area=_area(d(steel.soil_cement_diameter)),
        second_moment=put(SECOND_MOMENT, PI * ((outer - 2 * corrosion) ** 4 - (outer - 2 * wall) ** 4) / 64),
        unit_weight=unit_weight,
        minimum_embedment=put(LENGTH, d(steel.soil_cement_diameter) / (2 if half else 1)))


def has_pile(staggered: bool, along: int, across: int) -> bool:
    """Whether a pile stands at the 1-based column *along* × *across* (a staggered layout has every other one)."""
    return not staggered or (along + across) % 2 == 0


def _columns(positions: tuple[Printed, ...], counts: list[int]) -> tuple[PileColumn, ...]:
    first = d(positions[0])
    return tuple(PileColumn(count=count, distance=LENGTH(float(d(position) - first)))
                 for position, count in zip(positions, counts))


def _rows(pier: PierInput) -> PileRows:
    layout = pier.piles.layout
    staggered = layout.pattern == choices.STAGGERED
    along, across = len(layout.along), len(layout.across)
    removed = set(layout.removed)
    counts_along = [sum(1 for j in range(1, across + 1) if has_pile(staggered, i, j) and (i, j) not in removed)
                    for i in range(1, along + 1)]
    counts_across = [sum(1 for i in range(1, along + 1) if has_pile(staggered, i, j) and (i, j) not in removed)
                     for j in range(1, across + 1)]
    columns_along, columns_across = _columns(layout.along, counts_along), _columns(layout.across, counts_across)

    def intervals(columns: tuple[PileColumn, ...]) -> list[Decimal]:
        return [d(b.distance) - d(a.distance) for a, b in zip(columns, columns[1:])]

    spacing_along = LENGTH(float(intervals(columns_along)[0])) if along > 1 else LENGTH(0)
    spacing_across = LENGTH(float(intervals(columns_across)[0])) if across > 1 else LENGTH(0)
    # the area of the pile group as SOIL-JR's 群杭 check takes the intervals (Lm, Ln): a grid has the intervals, a
    # staggered layout twice the interval of the side that is the narrower (CONTEXT.md 千鳥配置, SOIL-JR 1.5)
    if staggered:
        wide = spacing_along.value / spacing_across.value >= 1.5 if spacing_across.value else True
        lm = (LENGTH(spacing_along.value if wide else 2 * spacing_along.value),
              LENGTH(2 * spacing_across.value if wide else spacing_across.value))
        wide = spacing_across.value / spacing_along.value >= 1.5 if spacing_along.value else True
        ln = (LENGTH(spacing_across.value if wide else 2 * spacing_across.value),
              LENGTH(2 * spacing_along.value if wide else spacing_along.value))
    else:
        lm, ln = (spacing_along, spacing_across), (spacing_across, spacing_along)
    piles = sum(counts_along)
    expected = along * across if not staggered else (along * across) // 2 + 1
    unequal = any(len(set(intervals(columns))) > 1 for columns in (columns_along, columns_across))
    return PileRows(
        pattern=2 if staggered else 1, along=columns_along, across=columns_across, spacing_along=spacing_along,
        spacing_across=spacing_across, lm=lm, ln=ln, rows_written=unequal or piles != expected,
        removed=tuple((j, i) for i, j in sorted(removed)), piles=piles)


def calculate_pile_ground(pier: PierInput) -> PileGroundResult:
    """The values of the .sdt of *pier* (a pile foundation; the parser checked the pile items)."""
    sub = pier.substructure
    depth = _mm(put(LENGTH, d(sub.h[6]) + d(sub.h[5]) + min(d(sub.df1), d(sub.df2))))
    length = _mm(pier.piles.length)
    water = depth - _mm(sub.hw2)
    if not -99_999 <= water <= 99_999:
        raise InputError(f"下部構造.水位.平水位_hw2: 地表から平水位までが範囲外です（{_length(water).value} m、"
                         "SOIL-JR は ±99.999 m）")
    bounds = _bounds(pier)
    rows = _along_pile(pier, bounds, depth, length)
    return PileGroundResult(
        foundation=sub.foundation, depth=_length(depth), length=_length(length), water_depth=_length(water),
        head=_head(pier, bounds, depth, water), layers=rows, section=_section(pier, rows), rows=_rows(pier),
        liquefaction=any(row.reduction is not None and row.reduction.value < 1 for row in rows))


__all__ = ["HeadGround", "PileColumn", "PileGroundResult", "PileRows", "PileSection", "SoilRow",
           "calculate_pile_ground"]
