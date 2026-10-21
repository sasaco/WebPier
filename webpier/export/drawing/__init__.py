"""配筋図 (decision 73, CONTEXT.md 配筋図): the beam, column and footing sections drawn with ezdxf from the bars of
the calc layer (calc.beam_rebar, calc.column_rebar with calc.detailing.ties, calc.footing_rebar.face_layout).

``drawing_dxf`` gives one DXF with the three figures side by side, each at its own scale (``sheet.scale_for``) and
titled with it; ``drawing_figures`` gives each figure on a page of its own at that scale as a PDF (the vector figure
of the report's 4.1, GridLayoutPdf's PdfFigure) with the same page as a PNG (its ``preview`` in the grid Excel). All
are the same bytes for the same input. A blank the figures need is an input error naming its path, raised before
anything is drawn.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .sheet import GAP, TEXT, Sheet, TextEntityAlignment, Vec2, bbox, dxf_bytes, figure_bytes, scale_for  # isort: skip

from ...inputs import PierInput
from .beam import beam_figure, draw_beam
from .column import column_figure, draw_column
from .footing import draw_footing, footing_figure

FIGURES = ("梁", "柱", "フーチング")  # the order of 4.1: (1) 梁 (2) 柱 (3) フーチング
TITLES = {"梁": "梁（柱前面の断面）", "柱": "柱（水平断面）", "フーチング": "フーチング（線路方向の断面）"}
_SPACE = 20.0  # paper mm between the figures of the DXF

__all__ = ["FIGURES", "drawing_dxf", "drawing_figures"]


@dataclass(frozen=True)
class _Figure:
    name: str
    data: Any
    draw: Callable[[Sheet, Any, Vec2], None]
    scale: int


def _figures(pier: PierInput) -> list[_Figure]:
    beam, column, footing = beam_figure(pier), column_figure(pier), footing_figure(pier)
    return [
        _Figure("梁", beam, draw_beam, scale_for(beam.layout.width.value, beam.layout.depth.value)),
        _Figure("柱", column, draw_column, scale_for(column.layout.width.value, column.layout.height.value)),
        _Figure("フーチング", footing, draw_footing, scale_for(footing.length.value, footing.height.value)),
    ]


def _alone(figure: _Figure) -> Sheet:
    sheet = Sheet(figure.scale)
    figure.draw(sheet, figure.data, Vec2(0, 0))
    return sheet


def drawing_figures(pier: PierInput) -> dict[str, tuple[bytes, bytes]]:
    """Each figure (FIGURES, in their order) as (PDF, PNG): one page at its scale, and that page as a picture."""
    return {figure.name: figure_bytes(_alone(figure)) for figure in _figures(pier)}


def drawing_dxf(pier: PierInput) -> bytes:
    """The three figures in one DXF: side by side on their lower edges, each titled with its name and scale."""
    figures = _figures(pier)
    sheet = Sheet(figures[0].scale)
    left = 0.0
    for figure in figures:
        extents = bbox.extents(_alone(figure).msp, fast=True)
        sheet.scale = figure.scale
        origin = Vec2(left - extents.extmin.x, -extents.extmin.y)
        figure.draw(sheet, figure.data, origin)
        title = f"{TITLES[figure.name]}　1:{figure.scale}"
        sheet.text(title, Vec2(left, extents.size.y + (TEXT + GAP) * sheet.p), TextEntityAlignment.BOTTOM_LEFT,
                   height=1.5 * TEXT * sheet.p)
        left += extents.size.x + _SPACE * figure.scale
    return dxf_bytes(sheet.doc)
