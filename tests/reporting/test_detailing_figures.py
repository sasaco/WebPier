"""0400 4.1 配筋要領 (decision 73): each 配筋図 (PDF, PNG) is put as it is, as vector artwork in a frame of the body
width from column 4, as many rows as its page needs at that width (at most 30), with its PNG as the grid Excel's
picture. The pages here are made by PyMuPDF, not by the drawing (export.drawing, which the report does not import)."""

import math

import pymupdf
from gridlayoutpdf import PdfFigure

from webpier.calc.detailing import calculate_detailing
from webpier.inputs import parse_input
from webpier.reporting.stages.detailing import build_detailing, content, figure_specs, grid_documents

from test_detailing_report import data

PITCH_X, PITCH_Y = 16.08, 15.48  # the grid (GridLayoutPdf 0.2.0)


def page(width: float, height: float) -> tuple[bytes, bytes]:
    """One page of *width* × *height* pt with a line, and the page at 144 dpi as PNG."""
    document = pymupdf.open()
    sheet = document.new_page(width=width, height=height)
    sheet.draw_line((0, 0), (width, height))
    return document.tobytes(no_new_id=True), sheet.get_pixmap(dpi=144, alpha=False).tobytes("png")


def test_a_figure_fills_the_body_width_and_the_rows_its_page_needs():
    wide, tall = page(400, 200), page(100, 600)
    specs = figure_specs({"beam": wide, "column": tall})
    beam, column = specs["beam"], specs["column"]
    assert isinstance(beam.block, PdfFigure) and (beam.left, beam.texts) == (4, ())
    # 26 columns are 418.08 pt; the 400 × 200 page needs 209.04 pt of it, 14 rows; the tall one more than 30 rows
    assert (beam.block.col_span, beam.block.rows) == (26, math.ceil(26 * PITCH_X / 2 / PITCH_Y)) == (26, 14)
    assert (column.block.col_span, column.block.rows) == (26, 30)
    assert (beam.block.data, beam.block.preview) == wide and beam.block.block_id == "0400/layout.beam.figure"


def test_the_figures_stand_in_4_1_of_the_report_and_its_workbook(tmp_path):
    result = calculate_detailing(parse_input(data()))
    specs = figure_specs({name: page(400, 200) for name in ("beam", "column", "footing")})
    keys = [unit.key.removeprefix("0400/") for unit in content(result, specs)]
    assert keys[:9] == ["heading", "layout.heading", "layout.beam.heading", "layout.beam", "layout.column.heading",
                        "layout.column", "layout.footing.heading", "layout.footing", keys[8]]
    path = build_detailing(result, specs).render(tmp_path / "0400.pdf", invariant=True)
    first = pymupdf.open(path)[0]
    assert first.get_drawings()  # the vector page, not a picture
    assert not first.get_images()
    assert len(grid_documents(result, specs)) == 1
