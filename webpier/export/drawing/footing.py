"""フーチングの断面 (decision 73, CONTEXT.md 配筋図): the footing cut along the track, (B7 + B8 + B9) × H6, with the
layers of both faces as calc.footing_rebar.face_layout places them.

As the sample Example橋脚2 06_照査の前提.pdf 6.1 (3), the 線路 bars lie in the plane of the section and are drawn as
lines, the 直角 bars cross it and are drawn as circles at their pitch, centred on the footing (the input gives the
pitch, not where the first bar lies). Both run between the outermost centres of their face from the ends. Each layer
is labelled with its direction and 'D25-ctc125' (with its layer when its direction has more than one on the face),
the stirrups under the section with 'D16-1.00組/m ctc250' (組 = legs per 1 m / 2, as the sample's 2本/m → 1.00組/m).
On the right the layers' centres from their faces and the height; under the section the length and the direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from .sheet import GAP, TEXT, Sheet, TextEntityAlignment, Vec2, fan, mm, number  # isort: skip

from ...calc.footing_rebar import FaceLayout, PlacedLayer, Stirrups, _stirrups, face_layout
from ...core.printed import Printed
from ...inputs import PierInput, choices
from .column import _direction

UPPER, LOWER = choices.BEAM_FACES
RAIL, CROSS = choices.REBAR_DIRECTIONS
_METRE = 1000


@dataclass(frozen=True)
class FootingFigure:
    length: Printed  # B7 + B8 + B9, mm
    height: Printed  # H6, mm
    faces: dict[str, FaceLayout]  # by face
    stirrups: dict[str, Stirrups]  # by direction


def footing_figure(pier: PierInput) -> FootingFigure:
    """What the footing section is drawn from; a blank it needs is an input error naming its path."""
    sub, footing = pier.substructure, pier.rebar.footing
    length = sum(Decimal(repr(sub.b[index].value)) for index in (7, 8, 9)) * _METRE
    height = Decimal(repr(sub.h[6].value)) * _METRE
    return FootingFigure(length=Printed(float(length), 1, "mm"), height=Printed(float(height), 1, "mm"),
                         faces={face: face_layout(footing, face) for face in choices.BEAM_FACES},
                         stirrups={direction: _stirrups(footing, direction) for direction in choices.REBAR_DIRECTIONS})


def stations(length: float, pitch: float, edge: float) -> list[float]:
    """The centres at *pitch* centred on the footing, between *edge* and length − *edge*."""
    middle = length / 2
    count = math.floor((middle - edge) / pitch + 1e-9)
    return [middle + k * pitch for k in range(-count, count + 1)]


def layer_text(face: FaceLayout, layer: PlacedLayer) -> str:
    many = sum(other.direction == layer.direction for other in face.layers) > 1
    return (f"{layer.layer}段目" if many else "") + f"D{mm(number(layer.diameter))}-ctc{mm(number(layer.pitch))}"


def stirrup_text(stirrups: Stirrups) -> str:
    sets = Decimal(repr(stirrups.legs.value)) / 2
    return f"D{mm(number(stirrups.diameter))}-{sets:.2f}組/m ctc{mm(number(stirrups.pitch))}"


def draw_footing(sheet: Sheet, figure: FootingFigure, origin: Vec2) -> None:
    """The footing section with its lower-left corner at *origin*."""
    p = sheet.p
    length, height = figure.length.value, figure.height.value
    gap, line = GAP * p, (TEXT + 2 * GAP) * p
    sheet.rectangle(*origin, *(origin + Vec2(length, height)))
    for face in (UPPER, LOWER):
        layout = figure.faces[face]
        edge = layout.layers[0].center.value
        count = len(layout.layers)
        for index, layer in enumerate(layout.layers):
            y = height - layer.center.value if face == UPPER else layer.center.value
            radius = layer.diameter.value / 2
            if layer.direction == RAIL:
                sheet.line(origin + Vec2(edge, y), origin + Vec2(length - edge, y))
                targets = []
            else:
                xs = stations(length, layer.pitch.value, edge)
                for x in xs:
                    sheet.circle(origin + Vec2(x, y), radius)
                targets = xs
            # the label: spread along the face, outside it
            x = length * (0.15 + 0.7 * index / max(count - 1, 1))
            elbow = origin + Vec2(x, height + 4 * line if face == UPPER else -4 * line)
            if targets:
                near = sorted(targets, key=lambda station: (station > x, abs(station - x)))[:3]  # left of the elbow
                fan(sheet, elbow, (origin + Vec2(station, y) for station in near), radius)
            else:
                sheet.arrow_to(elbow, origin + Vec2(x, y))
            sheet.label(elbow, 1, f"{layer.direction}方向", layer_text(layout, layer))

    # on the right: the layers' centres from their faces, the height
    right = 2 * line
    total = number(figure.height)
    for face in (UPPER, LOWER):
        centres = [number(layer.center) for layer in figure.faces[face].layers]
        points = sorted({total, *(total - c for c in centres)}) if face == UPPER else sorted({Decimal(0), *centres})
        sheet.chain(points, length, length + right, vertical=True, origin=origin)
    sheet.chain([Decimal(0), total], length, length + right + 2 * line, vertical=True, origin=origin)

    # under: the length, the direction, the stirrups
    below = -6 * line
    sheet.chain([Decimal(0), number(figure.length)], 0.0, below, vertical=False, origin=origin)
    _direction(sheet, "線路方向", origin + Vec2(length / 2, below - 2 * line), 0.0)
    cursor = below - 4 * line
    sheet.text("スターラップ", origin + Vec2(0, cursor), TextEntityAlignment.TOP_LEFT)
    for direction in choices.REBAR_DIRECTIONS:
        cursor -= TEXT * p + gap
        sheet.text(f"{direction}方向 {stirrup_text(figure.stirrups[direction])}", origin + Vec2(2 * p, cursor),
                   TextEntityAlignment.TOP_LEFT)
