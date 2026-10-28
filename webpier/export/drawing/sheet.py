"""The sheet the 配筋図 are drawn on: layers, the text and dimension styles, and the drafting parts (decision 73).

Model space is in mm. A figure is meant to be plotted at 1/scale, so its text, arrows and the offsets of its callouts
are paper millimetres × scale (``Sheet.p``). The figures print their own numbers (``mm``), so a dimension never shows
ezdxf's measurement.

The bytes are fixed: ``dxf_bytes`` writes the dates and GUIDs ezdxf fixes for testing and the version alone as
CREATED_BY_EZDXF, and ``figure_bytes`` draws the model space through PyMuPDF to one PDF page and its PNG. ezdxf is
imported before its drawing add-on, and the CLASSES section is registered in name order (ezdxf takes it from a set).
"""

from __future__ import annotations

import io
import math
import os
import tempfile
from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HOME = "webpier-ezdxf"  # under the temporary folder: the home of a process without one


def home() -> None:
    """ezdxf reads its config and keeps its font cache under the user's home and stops at import without one, as in
    the minimal environment structural-mcp starts the headless runner in: such a process gets a home under the
    temporary folder."""
    try:
        Path.home()
    except RuntimeError:
        os.environ["USERPROFILE"] = str(Path(tempfile.gettempdir()) / HOME)


home()

import ezdxf  # noqa: E402  (after home)
from ezdxf import bbox, units
from ezdxf.addons.drawing import Frontend, RenderContext, layout
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration, LineweightPolicy
from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend
from ezdxf.document import CREATED_BY_EZDXF, Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.fonts import fonts
from ezdxf.math import Vec2
from ezdxf.render.arrows import ARROWS

from ...core.printed import Printed

FONT = "msgothic.ttc"
TEXT_STYLE = "MSゴシック"
DIM_STYLE = "配筋寸法"
TEXT = 2.5  # paper mm
ARROW = 2.0
GAP = 0.6  # between a text and its line
MARGIN = 3.0  # around a figure on its PDF page
PREVIEW_DPI = 200  # the PNG of a figure
LAYERS = {"躯体": 7, "鉄筋": 1, "寸法": 3, "引出線": 3, "文字": 7}
SCALES = (20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 250, 300, 400, 500)
PAPER = 120.0  # the paper mm the larger side of a member fits in, at its scale
STACK = 3  # the lines the texts of narrow gaps in a row step out over (Sheet.chain)

__all__ = ["ARROW", "Drawing", "GAP", "STACK", "Sheet", "TEXT", "TextEntityAlignment", "Vec2", "bbox", "dxf_bytes",
           "fan", "mm", "figure_bytes", "number", "scale_for"]


def scale_for(*lengths: Decimal | float) -> int:
    """The smallest scale (1/n) of SCALES at which the longest of *lengths* (mm) fits in PAPER mm."""
    longest = max(float(length) for length in lengths)
    return next((scale for scale in SCALES if longest / scale <= PAPER), SCALES[-1])


def number(value: Printed) -> Decimal:
    """The decimal a person reads of a printed length."""
    return Decimal(repr(value.value))


def mm(value: Decimal | float) -> str:
    """A length as the figure prints it: the decimals it has, without trailing zeros (108, 145.75, 1533.3)."""
    text = format(Decimal(repr(float(value))) if isinstance(value, float) else value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class Sheet:
    """A DXF document with the layers, text style and dimension style of the drawing, at 1/*scale*."""

    def __init__(self, scale: int) -> None:
        self.scale = scale
        self.doc = ezdxf.new("R2018", setup=True, units=units.MM)
        for name, color in LAYERS.items():
            self.doc.layers.add(name, color=color)
        self.doc.styles.add(TEXT_STYLE, font=FONT)
        self.doc.dimstyles.new(DIM_STYLE, dxfattribs={
            "dimtxsty": TEXT_STYLE, "dimtxt": TEXT, "dimasz": ARROW, "dimscale": scale,
            "dimexo": 1.0, "dimexe": 1.0, "dimgap": GAP, "dimtad": 1, "dimtih": 0, "dimtoh": 0,
            "dimdec": 0, "dimzin": 8, "dimblk": "",
        })
        self.msp = self.doc.modelspace()

    @property
    def p(self) -> float:
        """1 paper mm in model mm. A sheet with several figures sets ``scale`` for each before drawing it."""
        return float(self.scale)

    def width(self, text: str, height: float | None = None) -> float:
        """The drawn width of *text* (model mm) at *height* (model mm, TEXT by default)."""
        return fonts.make_font(FONT, height or TEXT * self.p).text_width(text)

    def line(self, start: Vec2, end: Vec2, layer: str = "鉄筋") -> None:
        self.msp.add_line(start, end, dxfattribs={"layer": layer})

    def polyline(self, points: Sequence[tuple[float, float, float]], layer: str) -> None:
        """A closed polyline of (x, y, bulge) points."""
        self.msp.add_lwpolyline(points, format="xyb", close=True, dxfattribs={"layer": layer})

    def rectangle(self, x0: float, y0: float, x1: float, y1: float, layer: str = "躯体") -> None:
        self.polyline([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], layer)

    def rounded(self, x0: float, y0: float, x1: float, y1: float, radius: float, layer: str = "鉄筋") -> None:
        """A closed rectangle with its corners bent to *radius* (a hoop or a stirrup)."""
        bulge = math.tan(math.pi / 8)
        self.polyline([(x0 + radius, y0, 0), (x1 - radius, y0, bulge), (x1, y0 + radius, 0), (x1, y1 - radius, bulge),
                       (x1 - radius, y1, 0), (x0 + radius, y1, bulge), (x0, y1 - radius, 0),
                       (x0, y0 + radius, bulge)], layer)

    def circle(self, center: Vec2, radius: float) -> None:
        self.msp.add_circle(center, radius, dxfattribs={"layer": "鉄筋"})

    def text(self, text: str, at: Vec2, align: TextEntityAlignment, *, height: float | None = None,
             rotation: float = 0.0) -> None:
        entity = self.msp.add_text(text, height=height or TEXT * self.p, rotation=rotation,
                                   dxfattribs={"style": TEXT_STYLE, "layer": "文字"})
        entity.set_placement(at, align=align)

    def label(self, elbow: Vec2, side: int, upper: str, lower: str = "") -> float:
        """An underlined callout from *elbow* to the right (side +1) or left (−1): *upper* above, *lower* below.
        Returns the length of the underline."""
        gap = GAP * self.p
        length = max(self.width(upper), self.width(lower) if lower else 0.0) + 2 * gap
        end = elbow + Vec2(side * length, 0)
        self.line(elbow, end, "引出線")
        left = min(elbow.x, end.x) + gap
        self.text(upper, Vec2(left, elbow.y + gap), TextEntityAlignment.BOTTOM_LEFT)
        if lower:
            self.text(lower, Vec2(left, elbow.y - gap), TextEntityAlignment.TOP_LEFT)
        return length

    def arrow(self, tip: Vec2, direction: float) -> None:
        """An open arrow at *tip* pointing to *direction* (degrees)."""
        self.msp.add_arrow(ARROWS.open_30, tip, ARROW * self.p, direction, dxfattribs={"layer": "引出線"})

    def arrow_to(self, start: Vec2, tip: Vec2) -> None:
        self.line(start, tip, "引出線")
        self.arrow(tip, (tip - start).angle_deg)

    def to_bar(self, start: Vec2, center: Vec2, radius: float) -> None:
        """A leader that stops on the circle of a bar seen end on."""
        self.line(start, center + (start - center).normalize(radius), "引出線")

    def dimension(self, base: Vec2, p1: Vec2, p2: Vec2, text: str, *, angle: float = 0.0,
                  location: Vec2 | None = None) -> None:
        """A linear dimension printing *text*; *location* moves the text off the dimension line without a leader."""
        override = {"dimscale": self.scale} | ({"dimtmove": 2} if location is not None else {})
        self.msp.add_linear_dim(base=base, p1=p1, p2=p2, location=location, angle=angle, text=text,
                                dimstyle=DIM_STYLE, override=override, dxfattribs={"layer": "寸法"}).render()

    def chain(self, points: Sequence[Decimal], edge: float, at: float, vertical: bool, origin: Vec2) -> None:
        """Chained dimensions through *points* (mm along the axis from *origin*, ascending) on the line *at* across
        it, their extension lines from *edge*; a run of equal gaps is one dimension 'n×s=total'. A gap too narrow for
        its text has the text moved beside it, outwards (before the first gap, after the others); of narrow gaps in a
        row between others, each one line further out than the one before, from one to three lines (STACK)."""
        runs = _runs(points)
        stacked = 0  # narrow gaps between others just before this one
        for index, (start, end, text) in enumerate(runs):
            p1, p2 = (Vec2(edge, float(start)), Vec2(edge, float(end))) if vertical else (Vec2(float(start), edge),
                                                                                           Vec2(float(end), edge))
            base = Vec2(at, float(start)) if vertical else Vec2(float(start), at)
            location = None
            narrow = self.width(text) + GAP * self.p > float(end - start)
            if not (narrow and 0 < index < len(runs) - 1):
                stacked = 0
            if narrow:
                lift = (TEXT / 2 + GAP) * self.p
                if 0 < index < len(runs) - 1:  # between two others: over its gap, one to STACK lines further out
                    level = 1 + stacked % STACK
                    along, lift = (float(start) + float(end)) / 2, lift + level * (TEXT + 2 * GAP) * self.p
                    stacked += 1
                else:  # the first before its start, the last after its end
                    reach = self.width(text) / 2 + (GAP + ARROW) * self.p
                    along = float(start) - reach if index == 0 and len(runs) > 1 else float(end) + reach
                location = origin + (Vec2(at - lift, along) if vertical else Vec2(along, at + lift))
            self.dimension(origin + base, origin + p1, origin + p2, text, angle=90.0 if vertical else 0.0,
                           location=location)


def _runs(points: Sequence[Decimal]) -> list[tuple[Decimal, Decimal, str]]:
    """The dimensions of a chain through *points*: consecutive gaps equal to 0.1 mm (the printed positions) are one
    run, printed 'n×s=total' with s = total / n to 0.1 mm (the digits of the positions)."""
    gaps = [b - a for a, b in zip(points, points[1:])]
    found, first = [], 0
    for index in range(1, len(gaps) + 1):
        if index == len(gaps) or abs(gaps[index] - gaps[first]) > Decimal("0.1"):
            total, count = points[index] - points[first], index - first
            spacing = (total / count).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            found.append((points[first], points[index],
                          mm(total) if count == 1 else f"{count}×{mm(spacing)}={mm(total)}"))
            first = index
    return found


def fan(sheet: Sheet, elbow: Vec2, targets: Iterable[Vec2], radius: float) -> None:
    """Leaders from one *elbow* to several bars seen end on."""
    for target in targets:
        sheet.to_bar(elbow, target, radius)


def dxf_bytes(doc: Drawing) -> bytes:
    """The DXF of *doc* with fixed dates and GUIDs, so the same drawing gives the same bytes."""
    doc.ezdxf_metadata()[CREATED_BY_EZDXF] = ezdxf.__version__  # without the time of ezdxf.new()
    # ezdxf registers the CLASS of each type in use from a set, in an order that changes with the string hash seed of
    # the process: registered here first, by name
    doc.commit_pending_changes()
    for dxftype in sorted(doc.entitydb.dxf_types_in_use()):
        doc.classes.add_class(dxftype)
    stream = io.StringIO()
    fixed = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = True
    try:
        doc.write(stream)
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = fixed
    return stream.getvalue().encode("utf-8")


def figure_bytes(sheet: Sheet) -> tuple[bytes, bytes]:
    """The model space of *sheet* on one page at its scale (the extents and MARGIN paper mm around them), in black
    lines without background, as a PDF, and the same page as a PNG at PREVIEW_DPI on white (the preview the grid
    Excel shows in its place: the page's aspect ratio to the pixel)."""
    extents = bbox.extents(sheet.msp, fast=True)
    width = extents.size.x / sheet.p + 2 * MARGIN
    height = extents.size.y / sheet.p + 2 * MARGIN
    config = Configuration(background_policy=BackgroundPolicy.OFF, color_policy=ColorPolicy.BLACK,
                           lineweight_policy=LineweightPolicy.ABSOLUTE)
    backend = PyMuPdfBackend()
    Frontend(RenderContext(sheet.doc), backend, config=config).draw_layout(sheet.msp, finalize=True)
    page = layout.Page(width, height, layout.Units.mm, margins=layout.Margins.all(MARGIN))
    replay = backend.get_replay(page, settings=layout.Settings(scale=1 / sheet.p, fit_page=False))
    pdf = replay.doc.tobytes(no_new_id=True)  # without the random file identifier
    png = replay.doc[0].get_pixmap(dpi=PREVIEW_DPI, alpha=False).tobytes("png")
    return pdf, png
