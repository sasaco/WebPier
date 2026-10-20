"""Beam bar layout: the bars of 鉄筋.梁 placed in the section at the column face (decisions 59, 68).

The section is b = B1 wide and h = H2 + H3 deep, mm; the origin is its upper-left corner, x from the left face and y
down from the upper face.

- Each face (上, 下) has layers of one size. Layer 1's centre from its face is the cover c_1: given (指定), or the pure
  cover + the stirrup + half the bar (自動). Each layer inside lies one bar and its clear gap further in, the gaps
  equal: c_k = c_1 + (k − 1)·(bar + gap). The counts are as Capacita splits them by layer 1's: every layer but the
  last as many as layer 1, the last at most as many; layer 1 has two bars or more.
- Along a face layer 1's spacing is s = (b − 2e)/(n − 1), with e the side bars' centre from the side face when there
  are side bars, else the cover c_1 (Capacita has one spacing per face, rebar_ss). Layer 1 runs from e to b − e at s:
  x_j = b/2 + (j − (n − 1)/2)·s for j = 0 … n − 1, s kept exact and each position rounded to the printed mm
  (LENGTH_MM). A layer inside takes the middle m of layer 1's positions (when the rest is odd, the one left over is at
  the far end, as the column's: calc.column_rebar), so its bars lie under layer 1's. The upper face's layers lie at
  y = c_k, the lower face's at y = h − c_k.
- The side bars lie on both side faces at x = c_s and b − c_s, from their start below the upper face at their pitch:
  y = start + j·pitch for j = 0 … count − 1 (one bar: the start only, no pitch). c_s is given (指定), or the pure
  cover (+ the stirrup when the bars are inside it) + half the bar (自動).
- Two bars overlap when their centres are closer than the mean of their sizes, (d_a + d_b)/2; touching is no
  overlap. It is compared exactly (the squared distance). An overlap is a warning the editor shows, not an input
  error.

A blank is an input error naming its path when the layout uses it (decision 5): the stirrup's size only for an
automatic cover that needs it. What Capacita cannot be given (unequal gaps, layer counts it would split otherwise) is
an input error naming its path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Printed
from ..inputs import choices
from ..inputs.rebar import LENGTH_MM, BeamBars
from ._exact import d, put
from .column_check import MainBars, SideBars

_BEAM = "鉄筋.梁"
SIDE = "側面"  # the group of the side bars


@dataclass(frozen=True)
class BeamBar:
    x: Printed  # centre from the left face, mm
    y: Printed  # from the upper face
    diameter: Printed
    group: str  # choices.BEAM_FACES (上, 下), or SIDE
    layer: int  # of the face, 1 outermost; the side bars from the top, 1, 2, …


@dataclass(frozen=True)
class BeamLayout:
    width: Printed  # b, mm
    depth: Printed  # h, mm
    faces: dict[str, MainBars]  # by choices.BEAM_FACES
    centers: dict[str, tuple[Printed, ...]]  # each face's layer centres from the face, outermost first
    side: SideBars | None
    side_center: Printed | None  # the side bars' centre from the side faces
    bars: tuple[BeamBar, ...]  # the upper face's layers, the lower face's, the side bars (left, right at each height)
    overlaps: tuple[tuple[int, int], ...]  # pairs of indices into bars, i < j


def beam_section(b1: Printed, h2: Printed, h3: Printed) -> tuple[Printed, Printed]:
    """b = B1 and h = H2 + H3 of the section at the column face, mm, from the dimensions in m."""
    return put(LENGTH_MM, d(b1) * 1000), put(LENGTH_MM, (d(h2) + d(h3)) * 1000)


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _stirrup(beam: BeamBars) -> Printed:
    """The stirrup's size, needed by an automatic cover."""
    return _need(beam.stirrups.diameter, f"{_BEAM}.stirrups.diameter_mm")


def _side(beam: BeamBars) -> tuple[SideBars, Printed] | None:
    """The side bars and their centre from the side faces: given (指定), or the pure cover, the stirrup when the bars
    are inside it, and half the bar (自動)."""
    side, path = beam.side, f"{_BEAM}.side_bars"
    if side is None:
        return None
    diameter = _need(side.diameter, f"{path}.diameter_mm")
    count = _need(side.per_face_count, f"{path}.per_face_count")
    if _need(side.cover_mode, f"{path}.cover_mode") == choices.COVER_SPECIFIED:
        centre = _need(side.center, f"{path}.center_mm")
    else:
        pure = _need(beam.pure_cover, f"{_BEAM}.pure_cover_mm")
        inside = _need(side.stirrup_position, f"{path}.stirrup_position") == choices.STIRRUP_POSITIONS[0]
        centre = put(LENGTH_MM, d(pure) + (d(_stirrup(beam)) if inside else 0) + d(diameter) / 2)
    return SideBars(diameter=diameter, count=count, first=_need(side.start, f"{path}.start_mm"),
                    spacing=_need(side.pitch, f"{path}.pitch_mm") if count > 1 else None), centre


def _face(beam: BeamBars, face: str, width: Printed, side_center: Printed | None
          ) -> tuple[MainBars, tuple[Printed, ...], tuple[int, ...], Decimal]:
    """The main bars of *face*, the centres of its layers, their counts and the exact spacing along the face."""
    bars, path = beam.faces[face], f"{_BEAM}.faces.{face}"
    diameter = _need(bars.diameter, f"{path}.diameter_mm")
    count = _need(bars.count, f"{path}.count")
    if count < 2:
        raise InputError(f"{path}.count: 2本以上が必要です")
    if _need(bars.cover_mode, f"{path}.cover_mode") == choices.COVER_SPECIFIED:
        cover = _need(bars.center, f"{path}.center_mm")
    else:
        pure = _need(beam.pure_cover, f"{_BEAM}.pure_cover_mm")
        cover = put(LENGTH_MM, d(pure) + d(_stirrup(beam)) + d(diameter) / 2)
    counts, gaps = [count], set()
    for index, layer in enumerate(bars.inner_layers):
        here = f"{path}.inner_layers[{index}]"
        counts.append(_need(layer.count, f"{here}.count"))
        gaps.add(_need(layer.clear_gap, f"{here}.clear_gap_mm"))
    if len(gaps) > 1:
        raise InputError(f"{path}.inner_layers: 段のあきが一定ではないため表せません")
    if any(other != count for other in counts[1:-1]) or counts[-1] > count:
        raise InputError(f"{path}.inner_layers: 段の本数は、最後の段を除いて1段目と同じ、最後の段は1段目以下が必要です"
                         "（Capacita は1段目の本数で段に分けます）")
    edge = side_center if side_center is not None else cover
    spacing = (d(width) - 2 * d(edge)) / (count - 1)
    pitch = d(diameter) + d(gaps.pop()) if gaps else Decimal(0)
    centers = tuple(put(LENGTH_MM, d(cover) + k * pitch) for k in range(len(counts)))
    main = MainBars(diameter=diameter, per_layer=count, layers=len(counts), count=sum(counts), cover=cover,
                    layer_spacing=put(LENGTH_MM, pitch) if len(counts) > 1 else None,
                    spacing=put(LENGTH_MM, spacing))
    return main, centers, tuple(counts), spacing


def _along(width: Printed, spacing: Decimal, count: int) -> list[Printed]:
    """*count* positions at *spacing*, centred on the face."""
    middle, half = d(width) / 2, Decimal(count - 1) / 2
    return [put(LENGTH_MM, middle + (j - half) * spacing) for j in range(count)]


def _overlaps(bars: list[BeamBar]) -> tuple[tuple[int, int], ...]:
    found = []
    for i, a in enumerate(bars):
        for j in range(i + 1, len(bars)):
            b = bars[j]
            reach = (d(a.diameter) + d(b.diameter)) / 2
            if (d(a.x) - d(b.x)) ** 2 + (d(a.y) - d(b.y)) ** 2 < reach ** 2:
                found.append((i, j))
    return tuple(found)


def beam_layout(beam: BeamBars, width: Printed, depth: Printed) -> BeamLayout:
    """The bars of *beam* in its section *width* × *depth* (mm)."""
    side = _side(beam)
    side_center = None if side is None else side[1]
    faces, centers, bars = {}, {}, []
    for face in choices.BEAM_FACES:
        main, layers, counts, spacing = _face(beam, face, width, side_center)
        faces[face], centers[face] = main, layers
        positions = _along(width, spacing, counts[0])
        for layer, (center, count) in enumerate(zip(layers, counts), 1):
            y = center if face == choices.BEAM_FACES[0] else put(LENGTH_MM, d(depth) - d(center))
            start = (counts[0] - count) // 2  # the middle of layer 1's positions
            bars += [BeamBar(x, y, main.diameter, face, layer) for x in positions[start:start + count]]
    if side is not None:
        bars_of_side, centre = side
        right = put(LENGTH_MM, d(width) - d(centre))
        for j in range(bars_of_side.count):
            y = bars_of_side.first if j == 0 else put(LENGTH_MM, d(bars_of_side.first) + j * d(bars_of_side.spacing))
            bars += [BeamBar(centre, y, bars_of_side.diameter, SIDE, j + 1),
                     BeamBar(right, y, bars_of_side.diameter, SIDE, j + 1)]
    return BeamLayout(width=width, depth=depth, faces=faces, centers=centers, side=None if side is None else side[0],
                      side_center=side_center, bars=tuple(bars), overlaps=_overlaps(bars))
