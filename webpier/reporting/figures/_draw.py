"""Drawing pieces shared by the frame figures, in top-origin points.

Only composition of GridLayoutPdf commands: arrows, dimension lines, springs
and an arc. Text is measured by the GridLayoutPdf font registry.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

from gridlayoutpdf import FontRegistry, Line, Point, Polyline, Text, TextStyle

from ..styles import BODY, HEADING, SMALL

NODE_STYLE = HEADING  # frame.node: MS-Gothic 9.9 pt
MEMBER_STYLE = replace(HEADING, size=8)  # frame.member: MS-Gothic 8 pt
DIMENSION_STYLE = HEADING  # frame.dimension: MS-Gothic 9.9 pt
LOAD_STYLE = BODY  # load symbols and spring names, as Example2 08 p.8-1 / p.8-6
THIN = .12


def spread(desired: Sequence[float], halves: Sequence[float], gap: float, lower: float, upper: float,
           what: str) -> list[float]:
    """Centres in the given (ascending) order, at least half + gap + half apart, inside [lower, upper]."""
    centres: list[float] = []
    for index, (target, half) in enumerate(zip(desired, halves, strict=True)):
        minimum = lower + half if not index else centres[-1] + halves[index - 1] + gap + half
        centres.append(max(target, minimum))
    if centres:
        centres[-1] = min(centres[-1], upper - halves[-1])
    for index in range(len(centres) - 2, -1, -1):
        centres[index] = min(centres[index], centres[index + 1] - halves[index + 1] - gap - halves[index])
    if centres and centres[0] - halves[0] < lower - 1e-9:
        raise ValueError(f"{what}: 図の大きさに対して文字を配置できません")
    return centres


def arrow_head(tip: tuple[float, float], direction: tuple[float, float], *, length: float = 5.0,
               width: float = 3.4, stroke: float = .5) -> Polyline:
    """An open head ending at *tip*, pointing along *direction*."""
    ux, uy = direction
    norm = math.hypot(ux, uy)
    ux, uy = ux / norm, uy / norm
    bx, by = tip[0] - ux * length, tip[1] - uy * length
    px, py = -uy * width / 2, ux * width / 2
    return Polyline((Point(bx + px, by + py), Point(*tip), Point(bx - px, by - py)), stroke)


def vertical_dimension(x: float, top: float, bottom: float, extension_from: float) -> list[Line | Polyline]:
    """Extension lines from *extension_from*, the dimension line at *x*, arrows inside or (short) outside."""
    lines: list[Line | Polyline] = [Line(extension_from, top, x + 3, top, THIN),
                                    Line(extension_from, bottom, x + 3, bottom, THIN),
                                    Line(x, top, x, bottom, THIN)]
    if bottom - top >= 10:
        lines += [arrow_head((x, top), (0, -1), stroke=THIN), arrow_head((x, bottom), (0, 1), stroke=THIN)]
    else:  # a short interval: arrows outside, pointing at the extension lines
        lines += [Line(x, top - 7, x, top, THIN), arrow_head((x, top), (0, 1), stroke=THIN),
                  Line(x, bottom, x, bottom + 7, THIN), arrow_head((x, bottom), (0, -1), stroke=THIN)]
    return lines


def horizontal_dimension(y: float, left: float, right: float, extension_from: float) -> list[Line | Polyline]:
    lines: list[Line | Polyline] = [Line(left, extension_from, left, y + 3, THIN),
                                    Line(right, extension_from, right, y + 3, THIN),
                                    Line(left, y, right, y, THIN)]
    if right - left >= 10:
        lines += [arrow_head((left, y), (-1, 0), stroke=THIN), arrow_head((right, y), (1, 0), stroke=THIN)]
    else:
        lines += [Line(left - 7, y, left, y, THIN), arrow_head((left, y), (1, 0), stroke=THIN),
                  Line(right, y, right + 7, y, THIN), arrow_head((right, y), (-1, 0), stroke=THIN)]
    return lines


def zigzag(start: tuple[float, float], end: tuple[float, float], *, teeth: int = 4, amplitude: float = 2.5,
           stroke: float = .25) -> Polyline:
    """A spring between two points (straight leads of a quarter of the length at each end)."""
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    px, py = -uy, ux
    lead = length / 4
    points = [Point(x0, y0), Point(x0 + ux * lead, y0 + uy * lead)]
    step = (length - 2 * lead) / (2 * teeth)
    for index in range(1, 2 * teeth):
        along = lead + index * step
        side = amplitude if index % 2 else -amplitude
        points.append(Point(x0 + ux * along + px * side, y0 + uy * along + py * side))
    points += [Point(x0 + ux * (length - lead), y0 + uy * (length - lead)), Point(x1, y1)]
    return Polyline(tuple(points), stroke)


def arc(centre: tuple[float, float], radius: float, start: float, end: float, *, stroke: float = 1.0,
        steps: int = 24) -> tuple[Polyline, Polyline]:
    """An arc from angle *start* to *end* (degrees, counterclockwise in y-up), with its head at *end*."""
    cx, cy = centre
    angles = [math.radians(start + (end - start) * index / steps) for index in range(steps + 1)]
    points = tuple(Point(cx + radius * math.cos(a), cy - radius * math.sin(a)) for a in angles)
    turn = 1 if end > start else -1  # +1: counterclockwise in y-up
    a = angles[-1]
    tangent = (-math.sin(a) * turn, -math.cos(a) * turn)  # page coordinates (y down)
    return Polyline(points, stroke), arrow_head((points[-1].x, points[-1].y), tangent, stroke=stroke)


def subscripted(fonts: FontRegistry, x: float, baseline: float, base: str, suffix: str) -> list[Text]:
    """A symbol with a subscript (Kv, MP), as the equations draw it: 6.5 pt, 1.92 pt below."""
    width = fonts.measure(base, LOAD_STYLE).width
    return [Text(x, baseline, base, LOAD_STYLE), Text(x + width, baseline + 1.92, suffix, SMALL)]


def text_width(fonts: FontRegistry, text: str, style: TextStyle) -> float:
    return fonts.measure(text, style).width


def cap_height(fonts: FontRegistry, style: TextStyle) -> float:
    """The height of the digits above the baseline, for centring a label on a point."""
    metrics = fonts.measure("0123456789", style)
    return -metrics.ink_bounds.y if metrics.ink_bounds is not None else metrics.ascent
