"""The model figure (検討モデルの骨組図) drawn from a Frame: Example2 08 p.8-1, 10 p.10-1.

The figure shows the physical outline (dashed), the members (rigid ones
thicker), the nodes with their numbers, the member numbers in boxes, the
vertical dimensions, the springs at the support and, optionally, the footing
dimensions and the bearing types. It works for both directions: the outline
takes the B sizes along the track and the W sizes across it.

Every printed number is a Printed value: a member height, the height of a
node above the footing base (the base node is at y = 0, so its height is its
y), the pier height of the Frame (7.600 of 8-1) or an input size. Positions
are only drawing geometry; the figure never adds printed values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gridlayoutpdf import (
    Circle, Figure, LayoutContext, LayoutOverflowError, Line, MeasuredBlock, Point, Polyline, Rectangle, Text,
    measure_block,
)

from ...calc.frame import Direction, Frame, NodeRole
from ...core.printed import Printed
from ...inputs import PierInput
from ..numbers import printed
from ..styles import grid_units
from ._draw import (
    DIMENSION_STYLE, LOAD_STYLE, MEMBER_STYLE, NODE_STYLE, THIN, cap_height, horizontal_dimension, spread,
    subscripted, text_width, vertical_dimension, zigzag,
)

Polygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Outline:
    """The physical shape in frame coordinates (m), and the extent of the top body part for the bearings."""

    polygons: tuple[Polygon, ...]
    cap: tuple[float, float, float, float]  # left, right, bottom, top of the beam (or the top body part)


@dataclass(frozen=True)
class HorizontalDimension:
    """A dimension below the footing from x0 to x1 (m, frame x), printed as *text*, in row *row*."""

    x0: float
    x1: float
    text: str
    row: int

    def __post_init__(self) -> None:
        if not self.x1 > self.x0 or self.row < 0 or not self.text:
            raise ValueError("寸法線は x0 < x1、row ≥ 0、文字ありで指定してください")


def _f(value: Printed) -> float:
    return float(value.value)


def pier_outline(pier: PierInput, frame: Frame) -> Outline:
    """The pier elevation in the plane of *frame*, on its column axis (0600 shape rules)."""
    s = pier.substructure
    a = s.b if frame.direction is Direction.LONGITUDINAL else s.w
    h = {index: _f(value) for index, value in s.h.items()}
    a1, a3, a4, a5, a6, a7, a8, a9 = (_f(a[index]) for index in (1, 3, 4, 5, 6, 7, 8, 9))
    axis = _f(frame.node(NodeRole.CAP_TOP).x)
    zf, zc = h[5] + h[6], h[4] + h[5] + h[6]
    zb, zt = zc + h[3], zc + h[3] + h[2]
    half = (a7 + a8 + a9) / 2
    centre = axis + (a5 - a4) / 2  # beam centre
    lower = (a1 - a4 - a5) / 2  # half width of the haunch bottom, centred on the column
    polygons: list[Polygon] = []

    def add(bottom: float, top: float, bottom_x: tuple[float, float], top_x: tuple[float, float]) -> None:
        if top > bottom:
            polygons.append(((bottom_x[0], bottom), (bottom_x[1], bottom), (top_x[1], top), (top_x[0], top)))

    add(0.0, h[6], (-half, half), (-half, half))
    add(h[6], zf, (-half, half), (axis - a8 / 2, axis + a8 / 2))
    add(zf, zc, (axis - a6 / 2, axis + a6 / 2), (axis - a6 / 2, axis + a6 / 2))
    add(zc, zb, (axis - lower, axis + lower), (centre - a1 / 2, centre + a1 / 2))
    add(zb, zt, (centre - a1 / 2, centre + a1 / 2), (centre - a1 / 2, centre + a1 / 2))
    if frame.pedestal_section is not None:
        x = _f(frame.node(NodeRole.PEDESTAL_TOP).x)
        add(zt, zt + h[1], (x - a3 / 2, x + a3 / 2), (x - a3 / 2, x + a3 / 2))
    if h[2] > 0 or h[3] > 0:
        cap = (centre - a1 / 2, centre + a1 / 2, zc, zt)
    else:
        cap = (axis - a6 / 2, axis + a6 / 2, zf, zt)
    return Outline(tuple(polygons), cap)


def footing_dimensions(pier: PierInput, frame: Frame, total: Printed) -> tuple[HorizontalDimension, ...]:
    """B7 / B8 / B9 (W7 / W8 / W9 across the track) and the footing length *total* (0600), below the footing."""
    s = pier.substructure
    a = s.b if frame.direction is Direction.LONGITUDINAL else s.w
    left = -(_f(a[7]) + _f(a[8]) + _f(a[9])) / 2
    found = []
    for index in (7, 8, 9):
        width = _f(a[index])
        if width > 0:
            found.append(HorizontalDimension(left, left + width, printed(a[index]), 0))
        left += width
    found.append(HorizontalDimension(found[0].x0, found[-1].x1, printed(total), 1))
    return tuple(found)


@dataclass(frozen=True)
class FrameFigure:
    """The model figure as an atomic GridLayoutPdf block."""

    frame: Frame
    outline: Outline
    width: float = 528
    height: float = 432
    horizontal: tuple[HorizontalDimension, ...] = ()
    bearings: tuple[str, str] | None = None  # symbols at the origin side and the end side (M / F)
    block_id: str = ""

    # --- what is printed -------------------------------------------------------------------------------------
    def _base(self) -> None:
        if self.frame.node(NodeRole.FOOTING_BOTTOM).y.value != 0:
            raise ValueError("骨組図: footing bottom（フーチング底面の節点）が y = 0 にありません")

    def _dimensions(self) -> list[tuple[int, float, float, str]]:
        """(column, top y, bottom y, text) in metres: member heights; the pier height (beam top to footing
        top, calc) and the footing top; the top node above the base."""
        nodes = {node.number: node for node in self.frame.nodes}
        found = []
        for member in self.frame.members:
            if member.height.value > 0:
                a, b = nodes[member.start], nodes[member.end]
                top, bottom = max(a.y.value, b.y.value), min(a.y.value, b.y.value)
                found.append((0, top, bottom, printed(member.height)))
        footing = self.frame.node(NodeRole.FOOTING_TOP)
        found.append((1, self.frame.node(NodeRole.CAP_TOP).y.value, footing.y.value, printed(self.frame.pier_height)))
        found.append((1, footing.y.value, 0.0, printed(footing.y)))
        top = max(self.frame.nodes, key=lambda node: node.y.value)
        found.append((2, top.y.value, 0.0, printed(top.y)))
        return found

    def texts(self) -> tuple[str, ...]:
        """Every text run the figure draws, in drawing order."""
        self._base()
        found = [str(node.number) for node in self.frame.nodes]
        found += [str(member.number) for member in self.frame.members]
        found += [text for *_, text in self._dimensions()]
        found += [dimension.text for dimension in self.horizontal]
        found += ["K", "v", "K", "s", "K", "r"]
        found += list(self.bearings or ())
        return tuple(found)

    # --- drawing ---------------------------------------------------------------------------------------------
    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        self._base()
        fonts = context.fonts
        rows = 1 + max((d.row for d in self.horizontal), default=-1)
        left, top_margin = 46.0, 14.0
        right = 18 + 3 * 26 + (26 if self.bearings else 0)
        bottom = 42 + 22 * rows
        points = [(node.x.value, node.y.value) for node in self.frame.nodes]
        points += [point for polygon in self.outline.polygons for point in polygon]
        xs, ys = [x for x, _ in points], [y for _, y in points]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        wide, tall = self.width - left - right, self.height - top_margin - bottom
        if wide <= 0 or tall <= 0 or ymax <= ymin:
            raise LayoutOverflowError(f"{self.block_id or 'FrameFigure'}: 図の大きさが不足しています",
                                      block_id=self.block_id, needed=self.height, available=self.height)
        scale = min(wide / (xmax - xmin) if xmax > xmin else float("inf"), tall / (ymax - ymin))
        ox = left + (wide - (xmax - xmin) * scale) / 2 - xmin * scale

        def X(x: float) -> float:
            return ox + x * scale

        def Y(y: float) -> float:
            return top_margin + (ymax - y) * scale

        drawn: list = []
        texts: list[Text] = []
        for polygon in self.outline.polygons:
            for (x0, y0), (x1, y1) in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
                drawn.append(Line(X(x0), Y(y0), X(x1), Y(y1), .35, dash=(2, 2)))
        nodes = {node.number: (X(node.x.value), Y(node.y.value)) for node in self.frame.nodes}
        for member in self.frame.members:
            drawn.append(Line(*nodes[member.start], *nodes[member.end], 2.0 if member.rigid else .8))
        for number in sorted(nodes):
            drawn.append(Circle(*nodes[number], 1.7, fill=(0, 0, 0), stroke=False))
        for member in self.frame.members:
            (x0, y0), (x1, y1) = nodes[member.start], nodes[member.end]
            if not member.rigid and abs(y1 - y0) + abs(x1 - x0) < 3:
                drawn.append(Circle((x0 + x1) / 2, (y0 + y1) / 2, 3.5, stroke_width=.5))

        # Node numbers right of their nodes, spread so that close nodes (the micro member) stay readable.
        cap = cap_height(fonts, NODE_STYLE)
        support = self.frame.support.node
        order = sorted(nodes, key=lambda n: (nodes[n][1] - (7 if n == support else 0), n))
        centres = spread([nodes[n][1] - (7 if n == support else 0) for n in order], [cap / 2 + .5] * len(order),
                         1.5, 2, self.height - 2, "節点番号")
        for number, centre in sorted(zip(order, centres, strict=True)):
            x, y = nodes[number]
            texts.append(Text(x + 5, centre + cap / 2, str(number), NODE_STYLE))
            if abs(centre - y) > 1:
                drawn.append(Line(x + 1.5, y, x + 4.5, centre, THIN))

        # Member numbers in boxes left of the members.
        member_cap = cap_height(fonts, MEMBER_STYLE)
        mids = {m.number: ((nodes[m.start][0] + nodes[m.end][0]) / 2, (nodes[m.start][1] + nodes[m.end][1]) / 2)
                for m in self.frame.members}
        order = sorted(mids, key=lambda n: (mids[n][1], n))
        half = member_cap / 2 + 1.5
        centres = spread([mids[n][1] for n in order], [half] * len(order), 1.0, 2, self.height - 2, "部材番号")
        for number, centre in sorted(zip(order, centres, strict=True)):
            x, y = mids[number]
            label = str(number)
            width = text_width(fonts, label, MEMBER_STYLE) + 3
            box = x - 6 - width
            drawn.append(Rectangle(box, centre - half, width, 2 * half, .35))
            texts.append(Text(box + 1.5, centre + member_cap / 2, label, MEMBER_STYLE))
            if abs(centre - y) > 1:
                drawn.append(Line(x - 6, centre, x - 1, y, THIN))

        # Vertical dimensions right of the outline: member heights, the footing top, the top node.
        extent = max(max(X(x) for x in xs), *(x for x, _ in nodes.values()))
        if self.bearings:
            extent = max(extent, X(self.outline.cap[1]) + 22)
        columns = [extent + 18 + 26 * index for index in range(3)]
        dimensions = self._dimensions()
        placed: dict[int, float] = {}

        def wanted(top: float, low: float, label: str) -> float:
            """The middle of the interval, or just above it when it is far shorter than the text (the micro member)."""
            half = text_width(fonts, label, DIMENSION_STYLE) / 2
            return (Y(top) + Y(low)) / 2 if Y(low) - Y(top) >= half else Y(top) - half - 4

        for column in range(3):
            chosen = [(i, d) for i, d in enumerate(dimensions) if d[0] == column]
            chosen.sort(key=lambda item: (wanted(*item[1][1:]), item[0]))
            halves = [text_width(fonts, d[3], DIMENSION_STYLE) / 2 + .5 for _, d in chosen]
            centres = spread([wanted(*d[1:]) for _, d in chosen], halves, 4.0, 2, self.height - 2, "寸法")
            placed.update({i: c for (i, _), c in zip(chosen, centres, strict=True)})
        for index, (column, top, low, label) in enumerate(dimensions):
            x, a, b = columns[column], Y(top), Y(low)
            drawn.extend(vertical_dimension(x, a, b, extent + 3))
            centre, width = placed[index], text_width(fonts, label, DIMENSION_STYLE)
            texts.append(Text(x - 3, centre + width / 2, label, DIMENSION_STYLE, quarter_turns=1))
            if abs(centre - (a + b) / 2) > 1:
                drawn.append(Line(x, (a + b) / 2, x - 3, centre, THIN))

        # Footing dimensions below the springs.
        base = Y(0.0)
        for row in range(rows):
            chosen = [d for d in self.horizontal if d.row == row]
            y = base + 40 + 22 * row
            halves = [text_width(fonts, d.text, DIMENSION_STYLE) / 2 + 1 for d in chosen]
            centres = spread([(X(d.x0) + X(d.x1)) / 2 for d in chosen], halves, 3.0, 2, self.width - 2, "寸法")
            for dimension, centre in zip(chosen, centres, strict=True):
                x0, x1 = X(dimension.x0), X(dimension.x1)
                drawn.extend(horizontal_dimension(y, x0, x1, base + 3))
                width = text_width(fonts, dimension.text, DIMENSION_STYLE)
                texts.append(Text(centre - width / 2, y - 2.5, dimension.text, DIMENSION_STYLE))

        # Springs at the support (8-1): Kv down, Ks to the end side, Kr as a coil on the origin side.
        sx, sy = nodes[support]
        drawn += [zigzag((sx + 2, sy), (sx + 22, sy)), Line(sx + 22, sy - 4, sx + 22, sy + 4, .5),
                  zigzag((sx, sy + 2), (sx, sy + 22)), Line(sx - 4, sy + 22, sx + 4, sy + 22, .5),
                  _coil(sx - 13, sy + 9)]
        texts += subscripted(fonts, sx + 6, sy + 20, "K", "v")
        texts += subscripted(fonts, sx + 25, sy + 3.5, "K", "s")
        texts += subscripted(fonts, sx - 33, sy + 16, "K", "r")

        if self.bearings:
            cap_left, cap_right, cap_bottom, cap_top = self.outline.cap
            y = Y(cap_top) + min(10.0, (Y(cap_bottom) - Y(cap_top)) / 2)
            for symbol, x in zip(self.bearings, (X(cap_left) - 14, X(cap_right) + 14), strict=True):
                drawn.append(Circle(x, y, 6, stroke_width=.35))
                width = text_width(fonts, symbol, LOAD_STYLE)
                texts.append(Text(x - width / 2, y + cap_height(fonts, LOAD_STYLE) / 2, symbol, LOAD_STYLE))
        figure = Figure(grid_units(self.width), grid_units(self.height), *drawn, *texts, block_id=self.block_id)
        return measure_block(figure, context, available_width)


def _coil(x: float, y: float) -> Polyline:
    """The rotational spring: two turns of a spiral, as Example2 draws Kr."""
    points = []
    for step in range(49):
        angle = step / 48 * 4 * math.pi
        radius = 1 + 4 * step / 48
        points.append(Point(x + radius * math.cos(angle), y - radius * math.sin(angle)))
    return Polyline(tuple(points), .5)
