"""Load diagrams of the basic cases (荷重図) of 0620: Example2 09 pp.9-9..9-12.

The frame is drawn as a line with its nodes; each glyph is drawn at the node
or along the members it acts on, in the direction of its sign: N downward and
P (at the footing) downward for +, H toward +x (the end side, →) for +, M
clockwise for +. The values are printed beside the diagram by the stage; the
glyphs carry only their names.
"""

from __future__ import annotations

from dataclasses import dataclass

from gridlayoutpdf import (
    Arrow, Circle, Figure, LayoutContext, LayoutOverflowError, Line, MeasuredBlock, Text, measure_block,
)

from ...calc.frame import Frame
from ..styles import SMALL, grid_units
from ._draw import LOAD_STYLE, arc, arrow_head, cap_height, subscripted, text_width

KINDS = ("N", "H", "M", "P")


@dataclass(frozen=True)
class PointGlyph:
    """A load at a node: N (vertical, from above), H (horizontal), M (moment) or P (vertical, inclined arrow)."""

    node: int
    kind: str
    sign: int
    label: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS or self.sign not in (1, -1) or not self.label:
            raise ValueError(f"荷重図: 不明な荷重の記号です（{self.kind!r}, {self.sign!r}）")


@dataclass(frozen=True)
class AxialGlyph:
    """A vertical line load along *members*, drawn as a dashed arrow beside them (q of D1)."""

    members: tuple[int, ...]
    label: str


@dataclass(frozen=True)
class DistributedGlyph:
    """A horizontal load along members, linear from start to end; *labels* are (member, 0..1 along it, text).

    A segment is (member, start, end) over the whole member, or (member, start, end, t0, t1) over the part
    from t0 to t1 of its length (the wind above the ground, decision 12); a label's 0..1 is along that part.
    """

    segments: tuple[tuple[int, float, float] | tuple[int, float, float, float, float], ...]
    labels: tuple[tuple[int, float, str], ...]


Glyph = PointGlyph | AxialGlyph | DistributedGlyph


@dataclass(frozen=True)
class LoadDiagram:
    frame: Frame
    glyphs: tuple[Glyph, ...]
    width: float = 228
    height: float = 216
    block_id: str = ""

    def texts(self) -> tuple[str, ...]:
        """Every text run drawn, in order; a label ``M_P`` is two runs, M and its subscript P."""
        found: list[str] = []
        for glyph in self.glyphs:
            labels = [label for *_, label in glyph.labels] if isinstance(glyph, DistributedGlyph) else [glyph.label]
            for label in labels:
                found += [part for part in label.partition("_")[::2] if part]
        return tuple(found)

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        fonts = context.fonts
        left, right, top_margin, bottom = 60.0, 64.0, 46.0, 10.0
        xs = [node.x.value for node in self.frame.nodes]
        ys = [node.y.value for node in self.frame.nodes]
        wide, tall = self.width - left - right, self.height - top_margin - bottom
        if wide <= 0 or tall <= 0:
            raise LayoutOverflowError(f"{self.block_id or 'LoadDiagram'}: 図の大きさが不足しています",
                                      block_id=self.block_id, needed=self.height, available=self.height)
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        scale = min(wide / span_x if span_x else float("inf"), tall / span_y)
        ox = left + (wide - span_x * scale) / 2 - min(xs) * scale
        nodes = {node.number: (ox + node.x.value * scale, top_margin + (max(ys) - node.y.value) * scale)
                 for node in self.frame.nodes}
        members = {member.number: member for member in self.frame.members}
        drawn: list = [Line(*nodes[m.start], *nodes[m.end], .8) for m in self.frame.members]
        drawn += [Circle(*nodes[number], 1.5, fill=(0, 0, 0), stroke=False) for number in sorted(nodes)]
        texts: list[Text] = []
        cap = cap_height(fonts, LOAD_STYLE)

        placed: list[tuple[float, float, float, float]] = []

        def label(*candidates: tuple[float, float, str], value: str) -> None:
            """Put *value* at the first candidate (x, baseline, align) clear of the labels placed before.

            ``M_P`` is drawn as M with the subscript P.
            """
            base, _, suffix = value.partition("_")
            width = text_width(fonts, base, LOAD_STYLE) + (text_width(fonts, suffix, SMALL) if suffix else 0)
            for x, baseline, align in candidates:
                left = x - (width if align == "right" else width / 2 if align == "center" else 0)
                box = (left - 1, baseline - cap - 1, left + width + 1, baseline + 2)
                if not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
                    break
            placed.append(box)
            if suffix:
                texts.extend(subscripted(fonts, left, baseline, base, suffix))
            else:
                texts.append(Text(left, baseline, value, LOAD_STYLE))

        def node(number: int) -> tuple[float, float]:
            if number not in nodes:
                raise ValueError(f"荷重図: 節点 {number} は骨組にありません")
            return nodes[number]

        def member(number: int):
            if number not in members:
                raise ValueError(f"荷重図: 部材 {number} は骨組にありません")
            m = members[number]
            return nodes[m.start], nodes[m.end]

        for glyph in self.glyphs:
            if isinstance(glyph, PointGlyph):
                x, y = node(glyph.node)
                s = glyph.sign
                if glyph.kind == "N":
                    ends = ((x, y - 34), (x, y - 1)) if s > 0 else ((x, y - 1), (x, y - 34))
                    drawn.append(Arrow(*ends[0], *ends[1], head_length=5, head_width=3.4, width=.8))
                    label((x - 4, y - 28, "right"), (x + 4, y - 28, "left"), (x - 4, y - 16, "right"),
                          value=glyph.label)
                elif glyph.kind == "H":
                    tail = x - 36 * s
                    drawn.append(Arrow(tail, y, x - s, y, head_length=5, head_width=3.4, width=.8))
                    label((tail, y - 4, "center"), (tail, y + cap + 4, "center"), value=glyph.label)
                elif glyph.kind == "P":
                    ends = ((x - 14, y - 34), (x - 1, y - 1)) if s > 0 else ((x - 1, y - 1), (x - 14, y - 34))
                    drawn.append(Arrow(*ends[0], *ends[1], head_length=5, head_width=3.4, width=.8))
                    label((x - 17, y - 28, "right"), (x - 17, y - 16, "right"), value=glyph.label)
                else:  # M: clockwise over the top for +
                    drawn.extend(arc((x, y), 11, 160, 20) if s > 0 else arc((x, y), 11, 20, 160))
                    label((x + 15, y + cap / 2, "left"), (x + 15, y + cap / 2 + 12, "left"),
                          (x - 15, y + cap / 2, "right"), value=glyph.label)
            elif isinstance(glyph, AxialGlyph):
                ends = [member(number) for number in glyph.members]
                for (x0, y0), (x1, y1) in ends:
                    drawn.append(Line(x0 - 4, y0, x1 - 4, y1, .6, dash=(3, 2)))
                (x0, y0), (x1, y1) = ends[-1]
                drawn.append(arrow_head((x1 - 4, y1), (x1 - x0, y1 - y0 or 1), stroke=.6))
                (a, b), (c, e) = ends[0][0], ends[-1][1]
                label((min(a, c) - 8, (b + e) / 2 + cap / 2, "right"),
                      (min(a, c) - 8, (b + e) / 2 + cap / 2 + 12, "right"), value=glyph.label)
            else:
                parts = {segment[0]: (*segment, 0.0, 1.0)[:5] for segment in glyph.segments}

                def loaded(number: int) -> tuple[tuple[float, float], tuple[float, float]]:
                    (x0, y0), (x1, y1) = member(number)
                    t0, t1 = parts[number][3:]
                    return (x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0), (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)

                peak = max(abs(value) for segment in glyph.segments for value in segment[1:3]) or 1
                k = 36 / peak
                for number, start, end, *_ in glyph.segments:
                    (x0, y0), (x1, y1) = loaded(number)
                    a, b = x0 + 6 + abs(start) * k, x1 + 6 + abs(end) * k
                    drawn.append(Line(a, y0, b, y1, .5))
                    drawn += [Line(x0 + 6, y0, x1 + 6, y1, .3), Line(x0 + 6, y0, a, y0, .3),
                              Line(x1 + 6, y1, b, y1, .3)]
                    middle = (start + end) / 2
                    if middle and abs(y1 - y0) >= 8:
                        outer, inner = (a + b) / 2, (x0 + x1) / 2 + 6
                        tip, tail = (inner, outer) if middle < 0 else (outer - 1, inner)
                        if abs(tip - tail) >= 6:
                            drawn.append(Arrow(tail, (y0 + y1) / 2, tip, (y0 + y1) / 2, head_length=4,
                                               head_width=2.8, width=.3))
                for number, where, text in glyph.labels:
                    (x0, y0), (x1, y1) = loaded(number)
                    start, end = parts[number][1:3]
                    x = x0 + 6 + (abs(start) + (abs(end) - abs(start)) * where) * k + (x1 - x0) * where
                    baseline = y0 + (y1 - y0) * where + cap / 2
                    label((x + 3, baseline, "left"), (x + 3, baseline + 11, "left"), value=text)
        figure = Figure(grid_units(self.width), grid_units(self.height), *drawn, *texts, block_id=self.block_id)
        return measure_block(figure, context, available_width)
