"""梁の柱前面の断面 (decision 73, CONTEXT.md 配筋図): the beam section B1 × (H2 + H3) with its bars as calc places them.

The drawing is the section of calc.beam_rebar: x from the left face, y down from the upper face, as the sample
Example橋脚2 06_照査の前提.pdf 6.1 (1). It shows

- the bars of both faces and the side bars (calc.beam_rebar.BeamLayout.bars); the faces are labelled by layer above
  and under the section ('1段目D32-17本', '2段目D32-8本'), the side bars beside it with leaders to three of them
  ('D22-17本', on each side face);
- the stirrup round the bars of the faces, labelled 'D22-2組@125' (組 = 有効本数 / 2, as the column's hoops);
- the dimensions: above, the chain through the upper layer 1 and the width; under, the chain through the lower layer
  1 (both from the side bars' centre when there are side bars, calc.beam_rebar); on the left the layers' centres from
  their faces, the side bars' chain and the depth.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .sheet import GAP, TEXT, Sheet, TextEntityAlignment, Vec2, fan, mm, number  # isort: skip

from ...calc.beam_rebar import SIDE, BeamLayout, beam_layout, beam_section
from ...calc.cantilever.check import _stirrups
from ...calc.column_check import Hoops
from ...calc.detailing.ties import SETS
from ...inputs import PierInput, choices
from .column import printed

UPPER, LOWER = choices.BEAM_FACES


@dataclass(frozen=True)
class BeamFigure:
    layout: BeamLayout
    stirrups: Hoops  # diameter, 有効本数, pitch


def beam_figure(pier: PierInput) -> BeamFigure:
    """What the beam section is drawn from; a blank it needs is an input error naming its path."""
    sub = pier.substructure
    layout = beam_layout(pier.rebar.beam, *beam_section(sub.b[1], sub.h[2], sub.h[3]))
    return BeamFigure(layout=layout, stirrups=_stirrups(pier.rebar.beam))


def face_texts(layout: BeamLayout, face: str) -> list[str]:
    """'D32-17本' for each layer of *face*; with its layer when there are more than one."""
    bars = [bar for bar in layout.bars if bar.group == face]
    layers = sorted({bar.layer for bar in bars})
    diameter = mm(number(layout.faces[face].diameter))
    return [(f"{layer}段目" if len(layers) > 1 else "") + f"D{diameter}-{sum(bar.layer == layer for bar in bars)}本"
            for layer in layers]


def draw_beam(sheet: Sheet, figure: BeamFigure, origin: Vec2) -> None:
    """The beam section with its lower-left corner at *origin*."""
    layout = figure.layout
    p = sheet.p
    width, depth = float(layout.width.value), float(layout.depth.value)
    gap, line = GAP * p, (TEXT + 2 * GAP) * p

    def at(x: float, y: float) -> Vec2:  # y down from the upper face
        return origin + Vec2(x, depth - y)

    sheet.rectangle(*at(0, depth), *at(width, 0))
    for bar in layout.bars:
        sheet.circle(at(bar.x.value, bar.y.value), bar.diameter.value / 2)
    main = [bar for bar in layout.bars if bar.group != SIDE]
    half = figure.stirrups.diameter.value / 2
    left = min(bar.x.value - bar.diameter.value / 2 for bar in main) - half
    right = max(bar.x.value + bar.diameter.value / 2 for bar in main) + half
    top = min(bar.y.value - bar.diameter.value / 2 for bar in main) - half
    bottom = max(bar.y.value + bar.diameter.value / 2 for bar in main) + half
    largest = max(bar.diameter.value for bar in main)
    sheet.rounded(*at(left, bottom), *at(right, top), largest / 2 + half)

    # above: the chain of the upper layer 1, the width, the labels of the upper layers
    upper = _first_layer(layout, UPPER)
    sheet.chain([Decimal(0), *upper, number(layout.width)], depth, depth + 2 * line, vertical=False, origin=origin)
    sheet.chain([Decimal(0), number(layout.width)], depth, depth + 3.5 * line, vertical=False, origin=origin)
    cursor = depth + 4.5 * line
    for text in reversed(face_texts(layout, UPPER)):
        sheet.text(text, origin + Vec2(0, cursor), TextEntityAlignment.BOTTOM_LEFT)
        cursor += TEXT * p + gap

    # under: the labels of the lower layers, the chain of the lower layer 1
    cursor = -gap
    for text in face_texts(layout, LOWER):
        sheet.text(text, origin + Vec2(width / 2, cursor), TextEntityAlignment.TOP_CENTER)
        cursor -= TEXT * p + gap
    lower = _first_layer(layout, LOWER)
    sheet.chain([Decimal(0), *lower, number(layout.width)], 0.0, cursor - 2 * line, vertical=False, origin=origin)

    # on the left: the layers' centres from their faces, the side bars' chain, the depth (model y up)
    column = -2 * line
    height = number(layout.depth)
    for face in (UPPER, LOWER):
        centres = [number(c) for c in layout.centers[face]]
        points = sorted({height, *(height - c for c in centres)}) if face == UPPER else sorted({Decimal(0), *centres})
        sheet.chain(points, 0.0, column, vertical=True, origin=origin)
    sides = sorted({bar.y.value for bar in layout.bars if bar.group == SIDE})
    if sides:
        column -= 2 * line
        points = sorted({Decimal(0), height, *(height - Decimal(repr(y)) for y in sides)})
        sheet.chain(points, 0.0, column, vertical=True, origin=origin)
    sheet.chain([Decimal(0), height], 0.0, column - 2 * line, vertical=True, origin=origin)

    # on the right: the side bars, the stirrup
    elbow = at(width + 6 * p, depth / 2 - line)
    if sides:
        bars = sorted((bar for bar in layout.bars if bar.group == SIDE and bar.x.value > width / 2),
                      key=lambda bar: abs(bar.y.value - depth / 2))[:3]
        fan(sheet, elbow, (at(bar.x.value, bar.y.value) for bar in bars), bars[0].diameter.value / 2)
        diameter = mm(number(bars[0].diameter))
        sheet.label(elbow, 1, f"D{diameter}-{len(sides)}本")
    elbow = at(width + 6 * p, depth / 2 + 2 * line)
    leg = at(right, depth / 2 + 2 * line)
    sheet.arrow_to(elbow, leg)
    stirrups = figure.stirrups
    sets = printed(SETS(stirrups.legs / 2))
    sheet.label(elbow, 1, f"D{mm(number(stirrups.diameter))}-{sets}組@{mm(number(stirrups.pitch))}")


def _first_layer(layout: BeamLayout, face: str) -> list[Decimal]:
    return sorted({number(bar.x) for bar in layout.bars if bar.group == face and bar.layer == 1})
