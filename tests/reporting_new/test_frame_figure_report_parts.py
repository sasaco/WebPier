"""The frame-report parts beyond Example2's shapes: label fallbacks, distributed loads of either sign,
horizontal line loads (0620), different concretes, and the guards of the manuscript."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gridlayoutpdf import (
    Equation, Fraction, LayoutContext, LayoutOverflowError, Line, Root, Row, Text, measure_block,
)

from frame_report_cases import chain
from webpier.calc.frame import LineLoad, NodeRole, PointLoad, Region
from webpier.calc.materials import concrete
from webpier.core.printed import Printed
from webpier.reporting.document import report
from webpier.reporting.figures import AxialGlyph, DistributedGlyph, LoadDiagram, PointGlyph
from webpier.reporting.fonts import load_fonts
from webpier.reporting.stages.frame_report import (
    CaseLoads, Labelled, Manuscript, Span, TableSpec, blocks, case_glyphs, case_lines, plain, sub, table_block,
    used_concretes,
)
from webpier.reporting.styles import REPORT_STYLE, report_profile

FONTS = load_fonts()


def measure(block, width: float = 528):
    measured = measure_block(block, LayoutContext(FONTS, report_profile(), REPORT_STYLE), width)
    return [command for part in measured.parts for command in part.commands]


def frame(case: str = "current", stage: int = 2):
    return chain(case)[stage].frame


def test_labels_of_glyphs_at_one_node_move_to_free_places():
    f = frame()
    top = f.node(NodeRole.CAP_TOP).number
    glyphs = (PointGlyph(top, "N", 1, "N"), PointGlyph(top, "N", -1, "N'"), PointGlyph(top, "M", -1, "M"),
              PointGlyph(top, "M", 1, "M'"), PointGlyph(top, "H", 1, "H"), PointGlyph(top, "H", 1, "H'"),
              PointGlyph(f.node(NodeRole.FOOTING_CENTROID).number, "P", -1, "P"),
              PointGlyph(f.node(NodeRole.FOOTING_CENTROID).number, "M", 1, "M_P"))
    drawn = measure(LoadDiagram(f, glyphs), 240)
    texts = [c for c in drawn if isinstance(c, Text)]
    assert [c.text for c in texts] == ["N", "N'", "M", "M'", "H", "H'", "P", "M", "P"]
    assert texts[-1].style.size == pytest.approx(6.5) and texts[-1].y - texts[-2].y == pytest.approx(1.92)
    upright = [(round(c.x, 3), round(c.y, 3)) for c in texts[:6]]
    assert len(set(upright)) == 6


def test_distributed_loads_of_either_sign_and_axial_load_on_one_member():
    f = frame("pedestal")
    beam = next(m for m in f.members if m.region is Region.BEAM)
    column = next(m for m in f.members if m.region is Region.COLUMN)
    pedestal = next(m for m in f.members if m.region is Region.PEDESTAL)
    glyphs = (DistributedGlyph(((beam.number, 3.0, 3.0), (column.number, 1.0, 1.0), (pedestal.number, 1.0, 1.0)),
                               ((beam.number, .5, "w1"), (beam.number, .5, "w2"))),
              AxialGlyph((column.number,), "q"))
    drawn = measure(LoadDiagram(f, glyphs), 240)
    arrows = [c for c in drawn if isinstance(c, Line) and c.width == .3 and c.y1 == c.y2 and c.x1 != c.x2]
    # + loads point toward +x (away from the member); the short pedestal gets no arrow.
    shafts = [c for c in arrows if abs(c.x2 - c.x1) > 3 and c.x2 > c.x1]
    assert len(shafts) >= 2
    texts = [c for c in drawn if isinstance(c, Text)]
    assert [c.text for c in texts] == ["w1", "w2", "q"] and texts[0].y != texts[1].y


def test_a_load_diagram_too_small_is_a_layout_error():
    with pytest.raises(LayoutOverflowError):
        measure(LoadDiagram(frame(), (), width=120, height=48), 240)


def test_case_lines_list_horizontal_line_loads_and_all_zero_points():
    f = frame()
    line = LineLoad(tuple(m.number for m in f.column_line), Printed(0.0, 2, "kN/m"), Printed(-3.5, 2, "kN/m"))
    point = PointLoad(NodeRole.CAP_TOP, f.node(NodeRole.CAP_TOP).number, Printed(0.0, 2, "kN"),
                      Printed(0.0, 2, "kN"), Printed(0.0, 2, "kN m"))
    case = CaseLoads(1, "wind", (point,), (line,), horizontal=True)
    assert [plain(item) for item in case_lines(f, case)] == ["H = 0.00 kN", "qh = -3.50 kN/m"]
    glyphs = case_glyphs(f, case)
    assert isinstance(glyphs[-1], DistributedGlyph) and glyphs[-1].labels[0][2] == "qh"
    assert glyphs[0].kind == "H" and glyphs[0].sign == 1


def test_different_beam_and_column_concretes_are_printed_separately():
    f = frame(stage=2)
    materials = replace(f.materials, beam=concrete(Printed(24.0, 1, "N/mm2"), "x"))
    assert [(key, label) for key, label, _ in used_concretes(replace(f, materials=materials))] == \
        [("beam", "はり"), ("column", "柱")]
    seismic = chain("current")[3].frame
    assert [label for _, label, _ in used_concretes(seismic)] == ["柱"]


def test_a_label_that_would_cover_its_symbol_is_a_layout_error():
    m = Manuscript("x/")
    m.equation("long", "とても長い式の見出しの文字列", "A", "1 × 2", Printed(2.0, 2, "kN"))
    m.equation("plain", "", "B", "3")
    with pytest.raises(LayoutOverflowError, match="重なります"):
        report(*blocks(m.units[:1])).layout()
    assert report(*blocks(m.units[1:])).layout()


def test_plain_reads_every_node_kind():
    assert plain(Row(Fraction("1", "3"), Root("2"), sub("K", "v"))) == "1/3√2Kv" and plain(None) == ""
    assert plain(Labelled("柱", Equation("q", "1", result="1", unit="m"))) == "柱q=1=1m"
    assert plain([Span("a"), ("b",)]) == "ab"


def test_spanning_math_cells_are_centred_in_their_rows():
    spec = TableSpec((60, 60), ((Span(sub("D", "1"), rowspan=2), "a"), ("b",)), (14.28, 14.28), header_rows=0)
    drawn = measure(table_block(spec, "t"))
    assert [c.text for c in drawn if isinstance(c, Text)] == ["D", "1", "a", "b"]
