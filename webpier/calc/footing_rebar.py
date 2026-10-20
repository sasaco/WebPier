"""フーチングの配筋 (decisions 60, 68): what the footing section check (0810 / 0820) and the response values (0800) are
given from 鉄筋.フーチング.

Each direction (LONGITUDINAL 線路, TRANSVERSE 直角) reads its bars on the lower face, the tensile bars of the overhang,
and its stirrups; the upper bars are not read (the sample 12_フーチング.pdf 255 has no compression bars).

- The main bars per 1 m of width: each layer 1000／pitch bars, printed to 2 decimals, so a pitch that does not divide
  1 m gives a fraction (1000／130 = 7.69). Layer 1's centre from the lower face is center_mm when 指定, else the pure
  cover + half the bar for the direction outside (outer_direction), and the pure cover + that direction's bar + half
  its own for the other; each layer inside lies its bar and the clear gap past the previous layer of the direction.
  The layers are of one size. Capacita splits the total by layer 1's count (MemberGroup.cs, in double precision), so
  every layer but the last has as many bars as layer 1 and the last at most as many, the gaps are equal, and the
  split must come back to the number of layers. The effective depth of the 0800 effective width is measured to the
  centroid of the bars (owner, decision 68).
- The stirrups per 1 m of width: the density, or 1000／width_pitch_mm printed to 2 decimals; their pitch along the
  overhang.

The grades are the member's (materials.main, materials.transverse); f'ck is the footing concrete's
(鉄筋.フーチング.concrete_strength_mpa). Anything blank or not representable is an input error naming its path. The
check itself is Capacita's (ADR-0008).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput, choices
from ..inputs.rebar import FootingBars
from ._exact import d, put

_FOOTING = "鉄筋.フーチング"
LONGITUDINAL, TRANSVERSE = choices.REBAR_DIRECTIONS
_LOWER = choices.BEAM_FACES[1]
LENGTH_MM = Precision(1, "mm")
COUNT = Precision(2, "本")  # bars or legs per 1 m of width, fractional when the pitch does not divide 1 m (decision 68)
_METRE_MM = Decimal(1000)  # the bars are counted per 1 m of width (sample 12-255: D25@125 → D25-8本)


@dataclass(frozen=True)
class MainBars:
    """The lower (tensile) bars of the overhang in one direction, per 1 m of width, outermost layer first."""

    diameter: Printed  # mm, nominal (D25 → 25)
    counts: tuple[Printed, ...]  # per 1 m, by layer
    pitch: Printed  # mm, layer 1's
    cover: Printed  # mm, the centre of layer 1 from the lower face
    layer_spacing: Printed | None  # mm, centre to centre of the layers; None for one layer
    centroid: Printed  # mm, the centre of all the bars from the lower face
    grade: str

    @property
    def count(self) -> Printed:
        """All the layers, per 1 m."""
        return put(COUNT, sum(d(count) for count in self.counts))


@dataclass(frozen=True)
class Stirrups:
    """The shear reinforcement of the overhang in one direction, per 1 m of width."""

    diameter: Printed  # mm
    legs: Printed  # per 1 m of width
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


def _per_metre(spacing: Printed) -> Printed:
    return put(COUNT, _METRE_MM / d(spacing))


def _first_cover(footing: FootingBars, direction: str, here: str) -> Printed:
    face = footing.faces[_LOWER]
    bars = face.bars[direction]
    if _need(bars.cover_mode, f"{here}.cover_mode") == choices.COVER_SPECIFIED:
        return _need(bars.center, f"{here}.center_mm")
    pure = _need(footing.pure_cover, f"{_FOOTING}.pure_cover_mm")
    diameter = _need(bars.diameter, f"{here}.diameter_mm")
    outer = _need(face.outer_direction, f"{_FOOTING}.faces.{_LOWER}.outer_direction")
    if outer == direction:
        return put(LENGTH_MM, d(pure) + d(diameter) / 2)
    outside = _need(face.bars[outer].diameter, f"{_FOOTING}.faces.{_LOWER}.{outer}.diameter_mm")
    return put(LENGTH_MM, d(pure) + d(outside) + d(diameter) / 2)


def _main(footing: FootingBars, direction: str) -> MainBars:
    here = f"{_FOOTING}.faces.{_LOWER}.{direction}"
    bars = footing.faces[_LOWER].bars[direction]
    diameter = _need(bars.diameter, f"{here}.diameter_mm")
    pitch = _need(bars.pitch, f"{here}.pitch_mm")
    cover = _first_cover(footing, direction, here)
    counts, gaps = [_per_metre(pitch)], set()
    for index, layer in enumerate(bars.inner_layers):
        inner = f"{here}.inner_layers[{index}]"
        counts.append(_per_metre(_need(layer.pitch, f"{inner}.pitch_mm")))
        gaps.add(_need(layer.clear_gap, f"{inner}.clear_gap_mm"))
    if len(gaps) > 1:
        raise InputError(f"{here}.inner_layers: 段のあきが一定ではないため表せません")
    first, total = d(counts[0]), sum(d(count) for count in counts)
    if any(d(count) != first for count in counts[1:-1]) or d(counts[-1]) > first:
        raise InputError(f"{here}.inner_layers: 段の 1 m 当たり本数は、最後の段を除いて1段目と同じ、最後の段は1段目以下が"
                         "必要です（Capacita は1段目の本数で段に分けます）")
    if math.ceil(float(total) / float(first)) != len(counts):
        raise InputError(f"{here}.inner_layers: 1 m 当たり本数の合計 {float(total):g} を1段目の {float(first):g} で割ると、"
                         f"Capacita では{len(counts)}段になりません（小数の誤差）")
    spacing = put(LENGTH_MM, d(diameter) + d(gaps.pop())) if gaps else None
    centroid = cover if spacing is None else put(
        LENGTH_MM, sum(d(count) * (d(cover) + index * d(spacing)) for index, count in enumerate(counts)) / total)
    grade = _need(footing.materials.main, f"{_FOOTING}.materials.main")
    return MainBars(diameter=diameter, counts=tuple(counts), pitch=pitch, cover=cover, layer_spacing=spacing,
                    centroid=centroid, grade=grade)


def _stirrups(footing: FootingBars, direction: str) -> Stirrups:
    here = f"{_FOOTING}.stirrups.{direction}"
    row = footing.stirrups[direction]
    diameter = _need(row.diameter, f"{here}.diameter_mm")
    pitch = _need(row.pitch, f"{here}.pitch_mm")
    if _need(row.width_mode, f"{here}.distribution_mode") == choices.WIDTH_DENSITY:
        legs = put(COUNT, d(_need(row.density, f"{here}.density_per_m")))
    else:
        legs = _per_metre(_need(row.width_pitch, f"{here}.width_pitch_mm"))
    grade = _need(footing.materials.transverse, f"{_FOOTING}.materials.transverse")
    return Stirrups(diameter=diameter, legs=legs, pitch=pitch, grade=grade)


def footing_reinforcement(pier: PierInput, direction: str) -> FootingReinforcement:
    """The bars of the overhang in *direction* (LONGITUDINAL or TRANSVERSE) as the section check is given them."""
    footing = pier.rebar.footing
    return FootingReinforcement(direction=direction, main=_main(footing, direction),
                                stirrups=_stirrups(footing, direction), fck=pier.materials.footing)
