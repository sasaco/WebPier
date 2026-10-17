"""The 0600 shape figure: side and front views of the pier with the entered dimensions (m).

The outline is drawn from the input dimensions; every label is a printed input
value (the front view's soil cover is the soil depth at the column of the
result). Lines avoid the 0.3-0.9 pt stroke widths the PDF hand-check reads as
fraction bars.
"""

from __future__ import annotations

from dataclasses import dataclass

from gridlayoutpdf import (
    Arrow, Figure, Label, LayoutContext, Line, MeasuredBlock, Polyline, TextStyle, measure_block,
)

from ....calc.reaction.self_weight import SelfWeightResult
from ....core.printed import Printed
from ....inputs import PierInput
from ...numbers import printed
from ...styles import grid_units
from .manuscript import FigureSpec

DIMENSION = TextStyle(font="dimension", size=8.0)  # figure.dimension (Calibri 8 pt, 0600 p3)
CAPTION = TextStyle(font="caption", size=9.9)  # figure.caption (MS PGothic 9.9 pt, 0600 p3)
OUTLINE, THIN = 0.96, 0.24
WIDTH, HEIGHT = 458.64, 300.0
VIEW_WIDTH, VIEW_HEIGHT = 120.0, 190.0
TOP = 44.0  # the drawing starts below the caption and the beam dimension


@dataclass(frozen=True)
class View:
    """One view: the sizes across it (B or W), the common heights and the soil cover at both footing edges."""

    caption: str
    size: dict[int, Printed]
    heights: dict[int, Printed]
    soil: tuple[Printed, Printed]


def _views(pier: PierInput, sw: SelfWeightResult) -> tuple[View, View]:
    s = pier.substructure
    depth = sw.soil_depth_at_column
    return View("側 面 図", s.b, s.h, (s.df1, s.df2)), View("正 面 図", s.w, s.h, (depth, depth))


def _labels(view: View) -> list[str]:
    """Dimension labels in drawing order; zero sizes are not dimensioned."""
    size, h = view.size, view.heights
    labels = [printed(size[index]) for index in (1, 6, 4, 5, 7, 8, 9) if size[index].value]
    labels += [printed(h[index]) for index in (6, 5, 4, 3, 2, 1) if h[index].value]
    return labels + [printed(value) for value in view.soil]


def outline_figure(pier: PierInput, sw: SelfWeightResult) -> FigureSpec:
    views = _views(pier, sw)
    return FigureSpec("outline", tuple(text for view in views for text in (view.caption, *_labels(view))), views)


@dataclass(frozen=True)
class OutlineFigure:
    views: tuple[View, ...]
    block_id: str = ""

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        items: list = []
        for index, view in enumerate(self.views):
            items.extend(_draw(view, index * WIDTH / 2))
        return measure_block(Figure(grid_units(WIDTH), grid_units(HEIGHT), *items, block_id=self.block_id),
                             context, available_width)


def _label(x: float, y: float, text: str, style: TextStyle = DIMENSION) -> Label:
    return Label(x, y, text, style=style, align="center")


def _arrows(x1: float, y1: float, x2: float, y2: float) -> list:
    """A dimension line with arrow heads at both ends (a plain line when too short for heads)."""
    middle = ((x1 + x2) / 2, (y1 + y2) / 2)
    if abs(x2 - x1) + abs(y2 - y1) <= 10:
        return [Line(x1, y1, x2, y2, THIN)]
    return [Arrow(*middle, x1, y1, width=THIN, head_length=4, head_width=3),
            Arrow(*middle, x2, y2, width=THIN, head_length=4, head_width=3)]


def _horizontal(x1: float, x2: float, y: float, edge: float, text: str) -> list:
    """Dimension x1..x2 drawn at y, with extension lines from the outline at *edge*."""
    lines = [Line(x, min(y, edge) - 2, x, max(y, edge) + 2, THIN) for x in (x1, x2)]
    return [*lines, *_arrows(x1, y, x2, y), _label((x1 + x2) / 2, y - 2, text)]


def _vertical(y1: float, y2: float, x: float, edge: float, text: str, offset: float) -> list:
    lines = [Line(min(x, edge) - 2, y, max(x, edge) + 2, y, THIN) for y in (y1, y2)]
    return [*lines, *_arrows(x, y1, x, y2), _label(x + offset, (y1 + y2) / 2 + 3, text)]


def _draw(view: View, left: float) -> list:
    size = {index: value.value for index, value in view.size.items()}
    h = {index: value.value for index, value in view.heights.items()}
    total = size[7] + size[8] + size[9]
    footing_top = h[6] + h[5]
    column_top = footing_top + h[4]
    beam_top = column_top + h[3] + h[2]
    top = beam_top + h[1]
    axis = (size[7] - size[9]) / 2
    beam_left = axis + (size[5] - size[4]) / 2 - size[1] / 2
    ground = (footing_top + view.soil[0].value, footing_top + view.soil[1].value)
    scale = min(VIEW_WIDTH / max(total, size[1]), VIEW_HEIGHT / max(top, *ground))
    centre = left + WIDTH / 4 - 16

    def x(value: float) -> float:
        return centre + value * scale

    def y(value: float) -> float:
        return TOP + VIEW_HEIGHT - value * scale

    edges = (-total / 2, total / 2)
    lower = (beam_left + size[4], beam_left + size[1] - size[5])
    column = (axis - size[6] / 2, axis + size[6] / 2)
    items: list = [_label(centre, 11, view.caption, CAPTION)]
    items.append(Polyline(((x(edges[0]), y(0)), (x(edges[1]), y(0)), (x(edges[1]), y(h[6])),
                           (x(edges[1] - size[9]), y(footing_top)), (x(edges[0] + size[7]), y(footing_top)),
                           (x(edges[0]), y(h[6]))), OUTLINE, closed=True))
    items.append(Polyline(((x(column[0]), y(footing_top)), (x(column[0]), y(column_top)),
                           (x(column[1]), y(column_top)), (x(column[1]), y(footing_top))), OUTLINE))
    items.append(Polyline(((x(lower[0]), y(column_top)), (x(beam_left), y(column_top + h[3])),
                           (x(beam_left), y(beam_top)), (x(beam_left + size[1]), y(beam_top)),
                           (x(beam_left + size[1]), y(column_top + h[3])), (x(lower[1]), y(column_top))),
                          OUTLINE, closed=True))
    if h[1] and size[3]:
        pedestal = beam_left + size[2]
        items.append(Polyline(((x(pedestal), y(beam_top)), (x(pedestal), y(top)), (x(pedestal + size[3]), y(top)),
                               (x(pedestal + size[3]), y(beam_top))), OUTLINE))
    # The soil surface, straight between the covers at the footing edges.
    items.append(Line(x(edges[0]), y(ground[0]), x(edges[1]), y(ground[1]), THIN, dash=(3, 2)))
    labels = iter(_labels(view))
    items += _horizontal(x(beam_left), x(beam_left + size[1]), TOP - 8, y(top), next(labels))
    items += _horizontal(x(column[0]), x(column[1]), y(column_top) + 24, y(column_top), next(labels))
    for index, start, end in ((4, beam_left, lower[0]), (5, lower[1], beam_left + size[1])):
        if size[index]:
            items += _horizontal(x(start), x(end), y(column_top) + 12, y(column_top), next(labels))
    corners = (edges[0], edges[0] + size[7], edges[1] - size[9], edges[1])
    for index, start, end in zip((7, 8, 9), corners, corners[1:]):
        if size[index]:
            items += _horizontal(x(start), x(end), y(0) + 18, y(0), next(labels))
    level, right = 0.0, x(max(edges[1], beam_left + size[1])) + 34
    for index in (6, 5, 4, 3, 2, 1):
        if h[index]:
            items += _vertical(y(level), y(level + h[index]), right, x(edges[1]), next(labels), 16)
        level += h[index]
    for side, edge in enumerate(edges):
        position = x(edge) - 10 if side == 0 else x(edge) + 6
        cover = view.soil[side].value
        if cover:
            items += _vertical(y(footing_top), y(footing_top + cover), position, x(edge), next(labels),
                               -15 if side == 0 else 14)
        else:
            items.append(_label(position, y(footing_top) - 3, next(labels)))
    return items
