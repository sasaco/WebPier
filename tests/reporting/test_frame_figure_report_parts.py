"""The frame-report parts beyond Example2's shapes: different concretes, the guards of the manuscript and the
text of every node kind. The load diagrams are FEMPython's pages (decision 44)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gridlayoutpdf import (
    Equation, Fraction, LayoutContext, LayoutOverflowError, Root, Row, Text, measure_block,
)

from frame_report_cases import chain
from webpier.calc.materials import concrete
from webpier.core.printed import Printed
from webpier.reporting.document import report
from webpier.reporting.fonts import load_fonts
from webpier.reporting.stages.frame_report import (
    Labelled, Manuscript, Span, TableSpec, blocks, plain, sub, table_block, used_concretes,
)
from webpier.reporting.styles import REPORT_STYLE, report_profile

FONTS = load_fonts()


def measure(block, width: float = 528):
    measured = measure_block(block, LayoutContext(FONTS, report_profile(), REPORT_STYLE), width)
    return [command for part in measured.parts for command in part.commands]


def frame(case: str = "current", stage: int = 2):
    return chain(case)[stage].frame


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
    from gridlayoutpdf import BreakHint

    from webpier.reporting.equations import Definition, over, terms
    from webpier.reporting.stages.frame_report import Definitions

    assert plain(Row(over("1", "3"), Root("2"), sub("K", "v"))) == "1/3√2Kv" and plain(None) == ""
    # term stops and break hints print nothing; the operands and operators keep their order
    assert plain(Row(terms("2.000", "×", "(", "1", "+", "0.2", ")"), BreakHint())) == "2.000×(1 + 0.2)"
    assert plain(Definitions((Definition("V", "体積"), Definition("γ'", "単位体積重量")))) == "ここに、V：体積γ'：単位体積重量"
    with pytest.raises(TypeError):
        plain(Fraction("1", "3"))  # a stacked fraction is not written in these reports
    assert plain(Labelled("柱", Equation("q", "1", result="1", unit="m"))) == "柱q=1=1m"
    assert plain([Span("a"), ("b",)]) == "ab"


def test_spanning_math_cells_are_centred_in_their_rows():
    spec = TableSpec((60, 60), ((Span(sub("D", "1"), rowspan=2), "a"), ("b",)), (14.28, 14.28), header_rows=0)
    drawn = measure(table_block(spec, "t"))
    assert [c.text for c in drawn if isinstance(c, Text)] == ["D", "1", "a", "b"]
