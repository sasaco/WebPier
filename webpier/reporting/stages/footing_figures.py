"""The 0800 figures (decision 60, 12_フーチング.pdf 245〜247): the four shapes of the base pressure (Case 1〜4), the
effective width of the lower side, the base reaction on the overhang, and the self weight and overburden on it.

Every number drawn is a printed value of the calc result (the overhangs, the column width, H6, d, the bar centre,
L1, the cover depth, in m); the symbols (x, x1, x2, pd1, pd2, q1, q2, L1, ①, ②) are the sample's. The shapes are
schematic: the lengths across are scaled to the drawing, the heights separately, as the sample draws them.
"""

from __future__ import annotations

import math

from gridlayoutpdf import Arrow, Figure, Label, Line, Polyline, TextStyle

from ...calc.footing import EffectiveWidth, OverhangSide
from ...core.printed import Printed
from ..numbers import printed
from ..styles import BODY, PITCH
from .frame_report import FigureSpec

DIMENSION = TextStyle(font="dimension", size=8.0)  # figure.dimension (Calibri 8 pt, as the 0600 figures)
OUTLINE, THIN = 0.96, 0.24
FIGURE_LEFT = 117.0
HEAD = {"head_length": 4, "head_width": 3, "width": THIN}


def _label(x: float, y: float, text: str, style: TextStyle = DIMENSION, align: str = "center") -> Label:
    return Label(x, y, text, style=style, align=align)


def _arrows(x1: float, y1: float, x2: float, y2: float) -> list:
    """A dimension line with arrow heads at both ends (a plain line when too short for heads)."""
    middle = ((x1 + x2) / 2, (y1 + y2) / 2)
    if abs(x2 - x1) + abs(y2 - y1) <= 10:
        return [Line(x1, y1, x2, y2, THIN)]
    return [Arrow(*middle, x1, y1, **HEAD), Arrow(*middle, x2, y2, **HEAD)]


def _horizontal(x1: float, x2: float, y: float, edge: float, text: str, style: TextStyle = DIMENSION) -> list:
    """Dimension x1..x2 drawn at y with extension lines from the outline at *edge*, its text above the line."""
    lines = [Line(x, min(y, edge) - 2, x, max(y, edge) + 2, THIN) for x in (x1, x2)]
    return [*lines, *_arrows(x1, y, x2, y), _label((x1 + x2) / 2, y - 2, text, style)]


def _vertical(y1: float, y2: float, x: float, edge: float, text: str, offset: float = 4.0) -> list:
    """Dimension y1..y2 drawn at x with extension lines from the outline at *edge*, its text to the right."""
    lines = [Line(min(x, edge) - 2, y, max(x, edge) + 2, y, THIN) for y in (y1, y2)]
    return [*lines, *_arrows(x, y1, x, y2), _label(x + offset, (y1 + y2) / 2 + 3, text, align="left")]


def _spec(key: str, width: float, height: float, items: list, texts: tuple[str, ...]) -> FigureSpec:
    """The figure of *items*; its extent (set by the scaled data) is rounded up to the layout grid."""
    columns, rows = (math.ceil(extent / PITCH - 1e-9) for extent in (width, height))
    return FigureSpec(Figure(columns, rows, *items, block_id=key), texts, left=FIGURE_LEFT)


def _pressure(points: tuple[tuple[float, float], ...], base: float, step: float = 12.0) -> list:
    """The outline of a pressure shape below the base line at *base* (the points from the first edge), and the
    arrows from it up to the base."""
    items: list = [Polyline(((points[0][0], base), *points, (points[-1][0], base)), THIN)]
    x = points[0][0]
    while x <= points[-1][0] + 0.01:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if x1 - 0.01 <= x <= x2 + 0.01:
                y = y1 + (y2 - y1) * (x - x1) / (x2 - x1) if x2 > x1 else y1
                if y - base > HEAD["head_length"] + 0.5:  # an arrow needs at least its head
                    items.append(Arrow(x, y, x, base, **HEAD))
                break
        x += step
    return items


# --- 地盤反力形状 Case 1〜4 (sample 245) -----------------------------------------------------------------------------

_CELL_WIDTH, _CELL_HEIGHT, _CAPTION = 200.0, 84.0, 16.0
_DEPTH = 28.0  # pd1


def _case(ox: float, oy: float, name: str, profile: tuple[tuple[float, float], ...],
          dims: tuple[tuple[float, float, str], ...], labels: tuple[tuple[float, float, str, str], ...]) -> list:
    base = oy + 44
    items: list = [_label(ox + 8, oy + 10, name, BODY, "left"), Line(ox + 24, base, ox + 176, base, OUTLINE)]
    items += _pressure(tuple((ox + x, base + depth) for x, depth in profile), base)
    for x1, x2, text in dims:
        items += _horizontal(ox + x1, ox + x2, base - 12, base, text, BODY)
    for x, depth, text, align in labels:
        items.append(_label(ox + x, base + depth, text, BODY, align))
    return items


_CASES = (
    ("Case 1", ((30, _DEPTH), (150, 12)), ((30, 150, "x"),), ((26, _DEPTH, "pd1", "right"), (154, 14, "pd2", "left"))),
    ("Case 2", ((30, _DEPTH), (120, 0)), ((30, 120, "x"),), ((26, _DEPTH, "pd1", "right"),)),
    ("Case 3", ((30, _DEPTH), (80, _DEPTH), (140, 0)), ((30, 80, "x1"), (80, 140, "x2")),
     ((26, _DEPTH, "pd1=qd", "right"),)),
    ("Case 4", ((30, _DEPTH), (70, _DEPTH)), ((30, 70, "x"),), ((26, _DEPTH, "pd1=qd", "right"),)),
)


def cases_figure(key: str) -> FigureSpec:
    """The four shapes of the base pressure, two by two, under the caption 地盤反力形状."""
    items: list = [_label(0, 10, "地盤反力形状", BODY, "left")]
    texts = ["地盤反力形状"]
    for index, (name, profile, dims, labels) in enumerate(_CASES):
        ox, oy = (index % 2) * _CELL_WIDTH + 30, _CAPTION + (index // 2) * _CELL_HEIGHT
        items += _case(ox, oy, name, profile, dims, labels)
        texts += [name, *(text for _, _, text in dims), *(text for _, _, text, _ in labels)]
    return _spec(key, 2 * _CELL_WIDTH + 30, _CAPTION + 2 * _CELL_HEIGHT, items, tuple(texts))


# --- 2) 有効幅 (sample 246) --------------------------------------------------------------------------------------------

_WIDTH_DRAWN = 240.0


def width_figure(key: str, width: EffectiveWidth) -> FigureSpec:
    """The lower side: the footing with the column on it, the spread of d from the column faces to the lower bars
    (dashed), the overhangs across, the full width, H6, d and the bar centre."""
    full = width.full.value
    scale = _WIDTH_DRAWN / full
    scale_y = 72.0 / width.height.value
    x0, top = 60.0, 76.0
    bottom = top + width.height.value * scale_y
    bars = bottom - width.cover.value * scale_y
    left, right = x0 + width.left.value * scale, x0 + (width.left.value + width.column.value) * scale
    items: list = [Polyline(((x0, top), (x0 + _WIDTH_DRAWN, top), (x0 + _WIDTH_DRAWN, bottom), (x0, bottom)), OUTLINE,
                            closed=True),
                   Line(left, top - 30, left, top, OUTLINE), Line(right, top - 30, right, top, OUTLINE),
                   Line(left, top, left - width.left_effective.value * scale, bars, THIN, dash=(4, 2)),
                   Line(right, top, right + width.right_effective.value * scale, bars, THIN, dash=(4, 2)),
                   Line(left - width.left_effective.value * scale, bars, right + width.right_effective.value * scale,
                        bars, THIN)]
    texts = (printed(width.full), printed(width.left), printed(width.column), printed(width.right),
             printed(width.d), printed(width.cover), printed(width.height))
    items += _horizontal(x0, x0 + _WIDTH_DRAWN, 26, top - 30, texts[0])
    items += _horizontal(x0, left, 44, top - 30, texts[1])
    items += _horizontal(left, right, 44, top - 30, texts[2])
    items += _horizontal(right, x0 + _WIDTH_DRAWN, 44, top - 30, texts[3])
    edge = x0 + _WIDTH_DRAWN
    items += _vertical(top, bars, edge + 24, edge, texts[4])
    items += _vertical(bars, bottom, edge + 24, edge, texts[5])
    items += _vertical(top, bottom, edge + 56, edge, texts[6])
    return _spec(key, edge + 90, bottom + 12, items, texts)


# --- 3) 地盤反力による断面力 (sample 246) ----------------------------------------------------------------------------

_OVERHANG_DRAWN, _HEIGHT_DRAWN = 110.0, 70.0


def _column_face(x: float, top: float, bottom: float) -> list:
    """The column face: solid above the footing, dashed through it (the sample's break mark is not drawn)."""
    return [Line(x, top, x, bottom, OUTLINE), Line(x - 14, top + 6, x - 4, top - 6, THIN)]


def reaction_figure(key: str, side: OverhangSide, h6: Printed) -> FigureSpec:
    """The overhang of *side* with the base pressure under it: L1 and H6 printed, q1 at the edge, q2 at the column
    face, and the symbols L1 and x of the table below."""
    x0, top = 40.0, 36.0
    bottom, base = top + _HEIGHT_DRAWN, top + _HEIGHT_DRAWN + 8
    edge = x0 + _OVERHANG_DRAWN
    items: list = [*_column_face(x0, 10, top), Line(x0, top, x0, bottom, THIN, dash=(4, 2)),
                   Polyline(((x0, top), (edge, top), (edge, bottom), (x0, bottom)), OUTLINE),
                   Line(x0 - 20, bottom, edge, bottom, OUTLINE)]
    items += _pressure(((x0, base + 14), (edge, base + 26)), base)
    texts = (printed(side.length), printed(h6), "q1", "q2", "L1", "x")
    items += _horizontal(x0, edge, 24, top, texts[0])
    items += _vertical(top, bottom, edge + 24, edge, texts[1])
    items += [_label(edge + 6, base + 24, "q1", BODY, "left"), _label(x0 - 6, base + 12, "q2", BODY, "right")]
    items += _horizontal(x0 + 40, edge, base + 50, base + 30, "L1", BODY)
    items += _horizontal(x0, x0 + 60, base + 66, base + 30, "x", BODY)
    return _spec(key, edge + 70, base + 72, items, texts)


# --- 4) フーチング自重および上載土による断面力 (sample 247) --------------------------------------------------------------

def weight_figure(key: str, side: OverhangSide, h6: Printed) -> FigureSpec:
    """The overburden ① over the overhang and the footing ② of *side*: L1, the cover depth and H6 printed."""
    x0, top = 40.0, 36.0
    scale_y = 100.0 / (side.cover_depth.value + h6.value)
    middle = top + side.cover_depth.value * scale_y
    bottom = middle + h6.value * scale_y
    edge = x0 + _OVERHANG_DRAWN
    items: list = [*_column_face(x0, 10, top), Line(x0, top, x0, bottom, OUTLINE),
                   Line(x0, top, edge + 10, top, OUTLINE), Line(edge, top, edge, middle, THIN, dash=(4, 2)),
                   Line(x0, middle, edge, middle, THIN, dash=(4, 2)), Line(edge, middle, edge, bottom, OUTLINE),
                   Line(x0 - 20, bottom, edge, bottom, OUTLINE)]
    texts = (printed(side.length), printed(side.cover_depth), printed(h6), "①", "②")
    items += _horizontal(x0, edge, 24, top, texts[0])
    items += _vertical(top, middle, edge + 24, edge, texts[1])
    items += _vertical(middle, bottom, edge + 24, edge, texts[2])
    items += [_label((x0 + edge) / 2, (top + middle) / 2 + 3, "①", BODY), _label((x0 + edge) / 2, (middle + bottom) / 2 + 3, "②", BODY)]
    return _spec(key, edge + 70, bottom + 12, items, texts)
