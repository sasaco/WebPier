"""4.3 梁の構造細目: the detailing of the beam at the column face (decision 73; Example2 06 6.3〜6.8).

The bars are the beam layout (calc.beam_rebar) in the section b = B1, h = H2 + H3; the upper bars are the tensile bars
of the cantilever, the lower the compression bars.

- 1) (a) Pc = (upper + lower)／(b·h) ≧ 0.15 % (Example2 6.3(1): the side bars are not counted).
- ディープビーム (Example2 6.3(4)): the side bars of one face n·Aw／(b·h) and the stirrups' one leg Aw／(b·s) (the
  vertical bars of one face per its spacing) at least 0.08 % each, both at most min(2b, 300 mm) apart. Example2 counts
  the vertical bars over a length of the overhang; the ratio per spacing is the same without one.
- コーベル: the side bars of both faces 2·n·Aw ≧ 0.40·As of the upper bars, at most 300 mm apart.
- 圧縮鉄筋: As′ of the lower bars ≧ As／6 of the upper.
- 鉄筋のあき of each face: the least centre spacing along a layer and of neighbouring layers, less the bar; the limits
  are a beam's (20 mm, φ, 4/3 Dmax with the beam's Dmax).
- ps = legs·Aw／(b·s) ≧ 0.15 % of the stirrups.
- the spacing of the stirrups: ① 一般部 and ② 塑性ヒンジ部 (common), with d = h − the centroid of the upper bars, the
  compression bars the lower, the main bars the smaller of the upper and the lower, the short side min(b, h).

A beam without side bars has no deep beam or corbel bars of its sides: those checks are not satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import Printed
from ...inputs import PierInput, choices
from .._exact import d, put
from ..beam_rebar import BeamLayout, beam_layout, beam_section
from .common import (AREA, LENGTH, PERCENT, BarGroup, ClearSpacing, ShearRatio, SteelRatio, StirrupSpacing, bar_area,
                     bound, clear_spacing, confinement_spacing, count, general_spacing, least_gap, need, shear_ratio,
                     steel_ratio)

_BEAM = "鉄筋.梁"
UPPER, LOWER = choices.BEAM_FACES
# ディープビームの用心鉄筋: 0.08 % of the section on each face, at most 2·bw and 300 mm apart (RC標準 13.3.4;
# Example2 06 6.3(4))
SKIN_RATIO = Printed(0.08, 3, "%")
SKIN_SPACING = 300
# コーベルの用心鉄筋: 0.40·As, at most 300 mm apart (Example2 06 6.3(4))
CORBEL_FACTOR = Printed(0.4, 2, "")
CORBEL_SPACING = Printed(300, 0, "mm")
# 圧縮鉄筋: As／6 of the tensile bars (Example2 06 6.3(4) 片持ち梁の圧縮鉄筋)
COMPRESSION_DIVISOR = 6


@dataclass(frozen=True)
class SkinBars:
    """ディープビームの用心鉄筋 of one direction: area／(b·length) ≧ 0.08 %, spaced ≦ min(2b, 300 mm)."""

    diameter: Printed | None  # None: no side bars
    count: Printed  # the bars of one face (the horizontal), or 1 leg (the vertical)
    unit_area: Printed | None
    area: Printed  # count·Aw
    width: Printed  # b
    length: Printed  # h (the horizontal) or s (the vertical)
    ratio: Printed  # %
    minimum: Printed
    pitch: Printed | None
    spacing_limit: Printed  # min(2b, 300)
    ratio_ok: bool
    spacing_ok: bool  # also when there is one bar (no spacing)
    ok: bool  # bars, their ratio and their spacing


@dataclass(frozen=True)
class CorbelBars:
    tension: Printed  # As of the upper bars
    factor: Printed  # 0.40
    required: Printed  # 0.40·As
    diameter: Printed | None
    count: Printed  # one face
    unit_area: Printed | None
    provided: Printed  # both faces: 2·n·Aw
    pitch: Printed | None
    spacing_limit: Printed  # 300
    ok: bool


@dataclass(frozen=True)
class CompressionBars:
    tension: Printed  # As of the upper bars
    required: Printed  # As／6
    provided: Printed  # As′ of the lower bars
    ok: bool


@dataclass(frozen=True)
class BeamDetailing:
    width: Printed  # b, mm
    depth: Printed  # h, mm
    effective_depth: Printed  # d, mm
    fck: Printed
    aggregate_max: Printed
    amount: SteelRatio  # 1) (a): the upper, then the lower bars
    horizontal: SkinBars
    vertical: SkinBars
    corbel: CorbelBars
    compression: CompressionBars
    spacings: tuple[ClearSpacing, ClearSpacing]  # the upper and the lower face
    shear: ShearRatio
    general: StirrupSpacing
    confinement: StirrupSpacing

    @property
    def ok(self) -> bool:
        return all((self.amount.minimum_ok, self.horizontal.ok, self.vertical.ok, self.corbel.ok,
                    self.compression.ok, *(item.ok for item in self.spacings), self.shear.ok, self.general.ok,
                    self.confinement.ok))


def _face(layout: BeamLayout, face: str, aggregate_max: Printed) -> ClearSpacing:
    bars = [bar for bar in layout.bars if bar.group == face]
    lines: dict[int, list[Printed]] = {}
    for bar in bars:
        lines.setdefault(bar.layer, []).append(bar.x)
    centres = list({bar.y.value: bar.y for bar in bars}.values())
    return clear_spacing(least_gap(lines.values()), least_gap([centres]), layout.faces[face].diameter, aggregate_max,
                         column=False)


def _skin(diameter: Printed | None, number: Printed, width: Printed, length: Printed, pitch: Printed | None,
          path: str) -> SkinBars:
    unit = None if diameter is None else bar_area(diameter, path)
    area = put(AREA, Decimal(0) if unit is None else d(number) * d(unit))
    ratio = put(PERCENT, d(area) / (d(width) * d(length)) * 100)
    limit = min(bound("double_width", width, 2).value, bound("fixed_300", None, SKIN_SPACING).value, key=d)
    ratio_ok = d(ratio) >= d(SKIN_RATIO)
    spacing_ok = pitch is None or d(pitch) <= d(limit)
    return SkinBars(diameter=diameter, count=number, unit_area=unit, area=area, width=width, length=length,
                    ratio=ratio, minimum=SKIN_RATIO, pitch=pitch, spacing_limit=limit, ratio_ok=ratio_ok,
                    spacing_ok=spacing_ok, ok=diameter is not None and ratio_ok and spacing_ok)


def beam_detailing(pier: PierInput) -> BeamDetailing:
    beam, s = pier.rebar.beam, pier.substructure
    width, depth = beam_section(s.b[1], s.h[2], s.h[3])
    layout = beam_layout(beam, width, depth)
    aggregate_max = need(beam.aggregate_max, f"{_BEAM}.aggregate_max_mm")
    upper, lower = (BarGroup.of(layout.faces[face].diameter, count(layout.faces[face].count),
                                f"{_BEAM}.faces.{face}.diameter_mm") for face in (UPPER, LOWER))
    tops = [bar.y for bar in layout.bars if bar.group == UPPER]
    effective = put(LENGTH, d(depth) - sum((d(y) for y in tops), Decimal(0)) / len(tops))
    stirrups = beam.stirrups
    diameter = need(stirrups.diameter, f"{_BEAM}.stirrups.diameter_mm")
    legs = need(stirrups.effective_legs, f"{_BEAM}.stirrups.effective_legs")
    pitch = need(stirrups.pitch, f"{_BEAM}.stirrups.pitch_mm")
    side = layout.side
    side_diameter = None if side is None else side.diameter
    side_count = count(0 if side is None else side.count)
    side_pitch = None if side is None else (side.spacing or None)
    path = f"{_BEAM}.side_bars.diameter_mm"
    horizontal = _skin(side_diameter, side_count, width, depth, side_pitch, path)
    vertical = _skin(diameter, count(1), width, pitch, pitch, f"{_BEAM}.stirrups.diameter_mm")
    unit = None if side_diameter is None else bar_area(side_diameter, path)
    provided = put(AREA, Decimal(0) if unit is None else 2 * d(side_count) * d(unit))
    required = put(AREA, d(CORBEL_FACTOR) * d(upper.area))
    corbel = CorbelBars(tension=upper.area, factor=CORBEL_FACTOR, required=required, diameter=side_diameter,
                        count=side_count, unit_area=unit, provided=provided, pitch=side_pitch,
                        spacing_limit=CORBEL_SPACING,
                        ok=unit is not None and d(provided) >= d(required)
                        and (side_pitch is None or d(side_pitch) <= d(CORBEL_SPACING)))
    compression_required = put(AREA, d(upper.area) / COMPRESSION_DIVISOR)
    main = min(upper.diameter, lower.diameter, key=d)
    return BeamDetailing(
        width=width, depth=depth, effective_depth=effective, fck=pier.materials.beam, aggregate_max=aggregate_max,
        amount=steel_ratio((upper, lower), need(beam.materials.main, f"{_BEAM}.materials.main"), width, depth,
                           maximum=False), horizontal=horizontal, vertical=vertical, corbel=corbel,
        compression=CompressionBars(upper.area, compression_required, lower.area,
                                    d(lower.area) >= d(compression_required)),
        spacings=(_face(layout, UPPER, aggregate_max), _face(layout, LOWER, aggregate_max)),
        shear=shear_ratio(diameter, count(legs), width, pitch, f"{_BEAM}.stirrups.diameter_mm"),
        general=general_spacing(effective, lower.diameter, diameter, pitch),
        confinement=confinement_spacing(effective, main, diameter, min(width, depth, key=d), pitch))

