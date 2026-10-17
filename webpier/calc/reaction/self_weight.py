"""0600 pier self weight, overburden soil and buoyancy, with their centroids.

Coordinates: xL along the track and xC across it. The beam and the pedestal are
measured from the column axis, with heights from the beam top (up positive);
the column, the footing and the soil are measured from the footing centre, with
heights from the footing base. Water levels are heights above the footing base.

Volume tables print V, x and V·x to 3 decimals and weights to 2 (the 0600
self-weight pages); Example2 08 p.8-3 prints the footing, soil and buoyancy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...core.errors import InputError
from ...core.printed import AREA, FORCE, LENGTH, UNIT_WEIGHT, Precision, Printed
from ...inputs import PierInput
from .._exact import d, put, total

VOLUME = Precision(3, "m3")
VOLUME_MOMENT = Precision(3, "m4")
WEIGHT_MOMENT = Precision(3, "kN m")
# Buoyancy is the displaced volume times the unit weight of water, as a downward-negative load (08 p.8-3).
WATER = UNIT_WEIGHT.exact(-10.0)
ZERO = Decimal(0)


class Part(Enum):
    PEDESTAL = "pedestal"  # 桁受け
    BEAM = "beam"  # はり (prism and haunch)
    COLUMN = "column"  # 柱
    FOOTING = "footing"  # フーチング
    OVERBURDEN = "overburden"  # 上載土


@dataclass(frozen=True)
class VolumeRow:
    """One row of a volume table."""

    volume: Printed  # V (negative for a deduction)
    x_l: Printed  # centroid along the track
    x_c: Printed  # centroid across the track
    y: Printed | None  # centroid height; None where the table prints "-"
    moment_l: Printed  # V·xL
    moment_c: Printed  # V·xC
    moment_y: Printed | None  # V·y


@dataclass(frozen=True)
class Body:
    """Weight and centroid of one part, from its volume table."""

    rows: tuple[VolumeRow, ...]
    volume: Printed  # ΣV
    moment_l: Printed  # ΣV·xL
    moment_c: Printed  # ΣV·xC
    moment_y: Printed | None  # ΣV·y
    unit_weight: Printed  # γ
    weight: Printed  # N = ΣV × γ
    x_l: Printed  # xL = ΣV·xL / ΣV (the row's own value for a single prism)
    x_c: Printed  # xC
    y: Printed | None  # hG; None for soil and water, whose heights are not used


@dataclass(frozen=True)
class Buoyancy:
    """Buoyancy at one water level."""

    level: Printed  # water level above the footing base
    rise: Printed  # water above the lower soil surface, at most the soil-surface step |df1 − df2|
    wedge: Printed  # width along the track where the sloped soil surface is under water
    rectangle: Printed  # remaining width, where the submerged soil is a full rectangle
    body: Body  # rows: footing plan below the lower soil surface, column above the soil, wedge, rectangle


@dataclass(frozen=True)
class WeightRow:
    """One part in an aggregate about a reference point."""

    part: Part
    weight: Printed  # N
    x_l: Printed
    x_c: Printed
    y: Printed | None  # height above the reference; None for the soil (no height moment, as in the 0600 sheet)
    moment_l: Printed  # N·xL
    moment_c: Printed  # N·xC
    moment_y: Printed | None  # N·y


@dataclass(frozen=True)
class Aggregate:
    """Weights and centroid about a reference point."""

    rows: tuple[WeightRow, ...]
    weight: Printed  # ΣN
    moment_l: Printed
    moment_c: Printed
    moment_y: Printed
    x_l: Printed  # ΣN·xL / ΣN
    x_c: Printed
    y: Printed  # ΣN·y / ΣN


@dataclass(frozen=True)
class SelfWeightResult:
    pedestal_area: Printed  # B3 × W3
    pedestal: Body  # 桁受け, one prism of height H1 on the beam top
    beam_top_area: Printed  # A1 = B1 × W1
    beam_bottom_area: Printed  # A2 = (B1−B4−B5)(W1−W4−W5)
    beam_haunch_centroid: Printed  # z: haunch centroid above its lower (smaller) face A2
    beam: Body  # rows: prism (H2), haunch (H3)
    column_area: Printed  # B6 × W6
    column: Body  # one prism of height H4
    footing_length: Printed  # B = B7 + B8 + B9 (along the track)
    footing_width: Printed  # W = W7 + W8 + W9
    footing_top_area: Printed  # A1 = B8 × W8
    footing_bottom_area: Printed  # A2 = B × W
    footing_haunch_centroid: Printed  # z: haunch centroid above its lower (larger) face A2
    footing: Body  # rows: haunch (H5), prism (H6)
    soil_depth_at_column: Printed  # soil depth above the footing top at the column axis
    overburden: Body  # rows: trapezoid, column deduction, haunch layer, footing-haunch deduction
    buoyancy_high: Buoyancy  # hw1
    buoyancy_normal: Buoyancy  # hw2
    buoyancy_low: Buoyancy  # hw3
    pier_bottom: Aggregate  # pedestal, beam, column about the column bottom (Ds of the pier impact)
    footing_centre: Aggregate  # pedestal, beam, column, footing, soil about the footing base centre


def _row(volume: Printed, x_l: Printed, x_c: Printed, y: Printed | None = None) -> VolumeRow:
    return VolumeRow(
        volume=volume, x_l=x_l, x_c=x_c, y=y,
        moment_l=put(VOLUME_MOMENT, d(volume) * d(x_l)), moment_c=put(VOLUME_MOMENT, d(volume) * d(x_c)),
        moment_y=None if y is None else put(VOLUME_MOMENT, d(volume) * d(y)))


def _centroid(amount: Printed, moment: Printed, name: str) -> Printed:
    if amount.value == 0:
        if moment.value != 0:
            raise InputError(f"0600 {name}: 体積または重量の合計が0で、モーメントが0ではないため重心を求められません")
        return LENGTH(0)
    return put(LENGTH, d(moment) / d(amount))


def _body(name: str, rows: Sequence[VolumeRow], unit_weight: Printed) -> Body:
    volume = put(VOLUME, total(row.volume for row in rows))
    moment_l = put(VOLUME_MOMENT, total(row.moment_l for row in rows))
    moment_c = put(VOLUME_MOMENT, total(row.moment_c for row in rows))
    heights = [row.moment_y for row in rows if row.moment_y is not None]
    moment_y = put(VOLUME_MOMENT, total(heights)) if len(heights) == len(rows) else None
    if len(rows) == 1:
        x_l, x_c, y = rows[0].x_l, rows[0].x_c, rows[0].y
    else:
        x_l, x_c = _centroid(volume, moment_l, name), _centroid(volume, moment_c, name)
        y = None if moment_y is None else _centroid(volume, moment_y, name)
    return Body(rows=tuple(rows), volume=volume, moment_l=moment_l, moment_c=moment_c, moment_y=moment_y,
                unit_weight=unit_weight, weight=put(FORCE, d(volume) * d(unit_weight)), x_l=x_l, x_c=x_c, y=y)


def _area(a: Decimal, b: Decimal, name: str) -> Printed:
    area = put(AREA, a * b)
    if area.value <= 0:
        raise InputError(f"0600 {name}: 小数3桁に丸めた面積が0以下になります（寸法を確認してください）")
    return area


def _frustum_centroid(height: Printed, lower: Printed, upper: Printed) -> Printed:
    """Centroid of a frustum above its lower face: h/4·(1+2√r+3r)/(1+√r+r), r = upper/lower."""
    ratio = d(upper) / d(lower)
    root = ratio.sqrt()
    return put(LENGTH, d(height) / 4 * (1 + 2 * root + 3 * ratio) / (1 + root + ratio))


def _scaled(offset: Printed, z: Printed, height: Printed) -> Printed:
    """Centroid offset of a haunch whose section centre moves linearly to *offset* over *height*."""
    return LENGTH(0) if height.value == 0 else put(LENGTH, d(offset) * d(z) / d(height))


def _buoyancy(level: Printed, pier: PierInput, footing_area: Printed, column_area: Printed, column: Body,
              soil_depth: Printed, bf: Printed, wf: Printed) -> Buoyancy:
    s = pier.substructure
    df1, df2 = d(s.df1), d(s.df2)
    base, low, step = d(s.h[5]) + d(s.h[6]), min(df1, df2), abs(df1 - df2)
    hw = d(level)
    rise = put(LENGTH, min(hw - base - low, step))
    wet = max(d(rise), ZERO)
    wedge = put(LENGTH, min(d(bf) * wet / step, d(bf))) if step and wet else LENGTH(0)
    rectangle = put(LENGTH, d(bf) - d(wedge))
    half = d(bf) / 2
    if df1 > df2:  # the soil is lower at the end side: the wedge lies there
        wedge_x, rectangle_x = d(rectangle) + d(wedge) / 3 - half, d(rectangle) / 2 - half
    else:
        wedge_x, rectangle_x = 2 * d(wedge) / 3 - half, d(wedge) + d(rectangle) / 2 - half
    zero = LENGTH(0)
    rows = (
        _row(put(VOLUME, d(footing_area) * max(ZERO, min(low + base, hw))), zero, zero),
        _row(put(VOLUME, d(column_area) * max(hw - d(soil_depth) - base, ZERO)), column.x_l, column.x_c),
        _row(put(VOLUME, d(wedge) * d(wf) * wet / 2), put(LENGTH, wedge_x), zero),
        _row(put(VOLUME, d(rectangle) * d(wf) * wet), put(LENGTH, rectangle_x), zero),
    )
    return Buoyancy(level=level, rise=rise, wedge=wedge, rectangle=rectangle, body=_body("浮力", rows, WATER))


def _weight_row(part: Part, weight: Printed, x_l: Printed, x_c: Printed, y: Printed | None) -> WeightRow:
    return WeightRow(
        part=part, weight=weight, x_l=x_l, x_c=x_c, y=y,
        moment_l=put(WEIGHT_MOMENT, d(weight) * d(x_l)), moment_c=put(WEIGHT_MOMENT, d(weight) * d(x_c)),
        moment_y=None if y is None else put(WEIGHT_MOMENT, d(weight) * d(y)))


def _aggregate(name: str, rows: Sequence[WeightRow]) -> Aggregate:
    weight = put(FORCE, total(row.weight for row in rows))
    moments = [put(WEIGHT_MOMENT, total(getattr(row, key) for row in rows if getattr(row, key) is not None))
               for key in ("moment_l", "moment_c", "moment_y")]
    return Aggregate(rows=tuple(rows), weight=weight, moment_l=moments[0], moment_c=moments[1], moment_y=moments[2],
                     x_l=_centroid(weight, moments[0], name), x_c=_centroid(weight, moments[1], name),
                     y=_centroid(weight, moments[2], name))


def _shifted(a: Printed, b: Printed) -> Printed:
    return put(LENGTH, d(a) + d(b))


def calculate_self_weight(pier: PierInput) -> SelfWeightResult:
    s = pier.substructure
    b, w, h = ({i: d(v) for i, v in size.items()} for size in (s.b, s.w, s.h))
    gamma = s.unit_weight_body

    # 桁受け: geometric centroid even at zero volume (the drawing shows it).
    pedestal_area = put(AREA, b[3] * w[3])
    pedestal = _body("桁受け", [_row(put(VOLUME, d(pedestal_area) * h[1]),
                                     put(LENGTH, (2 * b[2] + b[3] - b[1] - b[4] + b[5]) / 2),
                                     put(LENGTH, (2 * w[2] + w[3] - w[1] - w[4] + w[5]) / 2),
                                     put(LENGTH, h[1] / 2))], gamma)

    # はり: the haunch frustum's centroid z is measured from its lower face A2 (ADR-0001).
    lower_b, lower_w = b[1] - b[4] - b[5], w[1] - w[4] - w[5]
    top_area, bottom_area = _area(b[1], w[1], "はり上面"), _area(lower_b, lower_w, "はり下面")
    beam_x_l, beam_x_c = put(LENGTH, (b[5] - b[4]) / 2), put(LENGTH, (w[5] - w[4]) / 2)
    z = _frustum_centroid(s.h[3], bottom_area, top_area)
    beam = _body("はり", [
        _row(put(VOLUME, d(top_area) * h[2]), beam_x_l, beam_x_c, put(LENGTH, -h[2] / 2)),
        _row(put(VOLUME, h[3] / 6 * (lower_b * w[1] + b[1] * lower_w + 2 * (d(top_area) + d(bottom_area)))),
             _scaled(beam_x_l, z, s.h[3]), _scaled(beam_x_c, z, s.h[3]), put(LENGTH, -(h[2] + h[3] - d(z)))),
    ], gamma)

    column_area = _area(b[6], w[6], "柱")
    column = _body("柱", [_row(put(VOLUME, d(column_area) * h[4]), put(LENGTH, (b[7] - b[9]) / 2),
                              put(LENGTH, (w[7] - w[9]) / 2), put(LENGTH, h[4] / 2 + h[5] + h[6]))], gamma)

    # フーチング: haunch frustum (H5) on the base prism (H6); z from the larger lower face.
    bf, wf = LENGTH.total(s.b[i] for i in (7, 8, 9)), LENGTH.total(s.w[i] for i in (7, 8, 9))
    footing_top, footing_bottom = put(AREA, b[8] * w[8]), _area(d(bf), d(wf), "フーチング下面")
    zf = _frustum_centroid(s.h[5], footing_bottom, footing_top)
    footing_haunch = _row(put(VOLUME, h[5] / 6 * (d(bf) * w[8] + b[8] * d(wf) + 2 * (d(footing_top) + d(footing_bottom)))),
                          _scaled(column.x_l, zf, s.h[5]), _scaled(column.x_c, zf, s.h[5]), put(LENGTH, h[6] + d(zf)))
    footing = _body("フーチング", [footing_haunch, _row(put(VOLUME, d(footing_bottom) * h[6]), LENGTH(0), LENGTH(0),
                                                    put(LENGTH, h[6] / 2))], s.unit_weight_footing)

    # 上載土: the soil surface is linear from df1 (origin side) to df2 (end side).
    df1, df2 = d(s.df1), d(s.df2)
    soil_depth = put(LENGTH, (df1 - df2) / d(bf) * (b[9] + b[8] / 2) + df2)
    trapezoid_x = put(LENGTH, d(bf) * (df1 + 2 * df2) / (3 * (df1 + df2)) - d(bf) / 2) if df1 + df2 else LENGTH(0)
    zero = LENGTH(0)
    overburden = _body("上載土", [
        _row(put(VOLUME, d(footing_bottom) * (df1 + df2) / 2), trapezoid_x, zero),
        _row(put(VOLUME, -d(column_area) * d(soil_depth)), column.x_l, column.x_c),
        # The haunch layer spans the whole footing plan, so it is centred on the footing (decision 20).
        _row(put(VOLUME, d(footing_bottom) * h[5]), zero, zero),
        _row(put(VOLUME, -d(footing_haunch.volume)), footing_haunch.x_l, footing_haunch.x_c),
    ], s.unit_weight_overburden)

    water = [_buoyancy(level, pier, footing_bottom, column_area, column, soil_depth, bf, wf)
             for level in (s.hw1, s.hw2, s.hw3)]

    # 柱下端: the pedestal enters by its weight and in the transverse moment (decision 20).
    top = h[4] + h[3] + h[2]
    pier_bottom = _aggregate("柱下端集計", [
        _weight_row(Part.PEDESTAL, pedestal.weight, pedestal.x_l, pedestal.x_c, put(LENGTH, top + d(pedestal.y))),
        _weight_row(Part.BEAM, beam.weight, beam.x_l, beam.x_c, put(LENGTH, top + d(beam.y))),
        _weight_row(Part.COLUMN, column.weight, zero, zero, put(LENGTH, h[4] / 2)),
    ])
    top += h[5] + h[6]
    footing_centre = _aggregate("フーチング中心集計", [
        _weight_row(Part.PEDESTAL, pedestal.weight, _shifted(pedestal.x_l, column.x_l),
                    _shifted(pedestal.x_c, column.x_c), put(LENGTH, top + d(pedestal.y))),
        _weight_row(Part.BEAM, beam.weight, _shifted(beam.x_l, column.x_l), _shifted(beam.x_c, column.x_c),
                    put(LENGTH, top + d(beam.y))),
        _weight_row(Part.COLUMN, column.weight, column.x_l, column.x_c, column.y),
        _weight_row(Part.FOOTING, footing.weight, footing.x_l, footing.x_c, footing.y),
        _weight_row(Part.OVERBURDEN, overburden.weight, overburden.x_l, overburden.x_c, None),
    ])
    return SelfWeightResult(
        pedestal_area=pedestal_area, pedestal=pedestal,
        beam_top_area=top_area, beam_bottom_area=bottom_area, beam_haunch_centroid=z, beam=beam,
        column_area=column_area, column=column,
        footing_length=bf, footing_width=wf, footing_top_area=footing_top, footing_bottom_area=footing_bottom,
        footing_haunch_centroid=zf, footing=footing,
        soil_depth_at_column=soil_depth, overburden=overburden,
        buoyancy_high=water[0], buoyancy_normal=water[1], buoyancy_low=water[2],
        pier_bottom=pier_bottom, footing_centre=footing_centre,
    )
