"""0620 PDF: the drawn text is the manuscript, bytes are deterministic, the pages follow the common grid,
and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Text

from frame_report_cases import TRANSVERSE_CASES, transverse_chain
from frame_report_pdf_checks import (
    BODY, HEADING, band_errors, column_x, drawn_order_errors, first, outside_body, placement_errors, relation_centres, row_bands, row_offset,
    spans, table_checks,
)
from pdf_handcheck import formula_checks
from test_longitudinal_report_pdf import PAGE_NUMBER, ROOT, measure, squeeze
from webpier.core.printed import Printed
from load_diagram_support import PAGES, REPORT, inserted, layout
from webpier.reporting.stages.transverse import PREFIX, content, render_transverse, semantic_records


def render(case: str, path: Path) -> Path:
    pier, reaction, result, _ = transverse_chain(case)
    return render_transverse(result, reaction, pier, path, REPORT)


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, reaction, result, _ = transverse_chain(case)
    before, after = layout(content(result, reaction, pier), PREFIX)
    pages = before + after
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text)]
    assert drawn_order_errors(squeeze("".join(drawn)), content(result, reaction, pier)) == []
    with pymupdf.open(render(case, tmp_path / "0620.pdf")) as pdf:
        # Decision 44: the load diagram pages come right after 9.3, and 9.4 starts the next page.
        assert len(pdf) == len(pages) + PAGES
        assert [inserted(page) for page in pdf] == [False] * len(before) + [True] * PAGES + [False] * len(after)
        assert "9.3 荷重図" in pdf[len(before) - 1].get_text()
        assert pdf[len(before) + PAGES].get_text().lstrip().startswith("9.4 設計作用の組合せ")
        for page, scene in zip([page for page in pdf if not inserted(page)], pages):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert not PAGE_NUMBER.search(page.get_text())
            assert not page.get_images()


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_every_printed_formula_and_table_row_recomputes_from_the_printed_numbers(tmp_path: Path, case: str):
    path = render(case, tmp_path / "0620.pdf")
    formulas = formula_checks(path)
    assert len(formulas) >= 20
    assert [check for check in formulas if not check.ok] == []
    rows = table_checks(path)
    kinds = Counter(check.kind for check in rows)
    # D1, D2, 3 snow, 3 train, 6 impact tables, 2 wind tables (+3 centrifugal on a curve, −3 snow without: decision 69)
    pier, _, result, _ = transverse_chain(case)
    assert kinds["total"] == 13 + (3 if result.centrifugal is not None else 0) + (3 if result.snow is not None else 0)
    assert kinds["row"] >= 80 - (0 if result.snow is not None else 18)  # 6 bearing rows in each snow table
    assert [check for check in rows if not check.ok] == []


def test_a_wrong_printed_number_is_caught_by_the_hand_check(tmp_path: Path):
    pier, reaction, result, _ = transverse_chain("current")
    table = result.train.up
    wrong = replace(table, rows=(replace(table.rows[0], n=Printed(table.rows[0].n.value + .01, 2, "kN")),
                                 *table.rows[1:]))
    path = render_transverse(replace(result, train=replace(result.train, up=wrong)), reaction, pier, tmp_path / "w.pdf",
                             REPORT)
    assert [check.kind for check in table_checks(path) if not check.ok] == ["row", "total"]


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import transverse_chain\n"
              "from load_diagram_support import REPORT\n"
              "from webpier.reporting.stages.transverse import render_transverse\n"
              "pier, reaction, result, _ = transverse_chain('current')\n"
              "render_transverse(result, reaction, pier, sys.argv[1], REPORT)\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render("curve", tmp_path / "d.pdf").read_bytes() != first


def test_the_pages_follow_the_grid_contract(tmp_path: Path):
    """As 0610 (test_longitudinal_report_pdf): the heading and body columns and faces, the figure, the result "="
    before column 22, nothing beyond the body, and the coefficient table (9-14) of whole grid rows, its Define cases
    as rows (17 on a curve)."""
    with pymupdf.open(render("curve", tmp_path / "0620.pdf")) as pdf:
        found = spans(pdf)
        placed = (("§9. 線路直角方向の計算（地震時以外）", 0, HEADING), ("9.2 作用の計算", 1, HEADING), ("(8) 風荷重", 2, HEADING),
                  ("1) 列車荷重がある場合", 3, HEADING), ("鉛直力は列車荷重に桁の衝撃係数を乗じた値とする．", 4, BODY))
        assert [error for text, column, face in placed for error in placement_errors(first(found, text), column, face)] == []
        assert len({round(row_offset(first(found, text)), 2) for text, *_ in placed}) == 1
        page_one = [span for span in found if span.page == 1]
        assert any(span.text == "1" and (span.face, span.size) == (HEADING, 10.0) for span in page_one)
        assert any(span.text == "1" and (span.face, span.size) == (HEADING, 8.0) for span in page_one)
        dimension = first(found, "4.900")
        assert (dimension.face, dimension.size, dimension.upright) == (HEADING, 10.0, False)
        centres = relation_centres(pdf, 22)
        assert len(centres) >= 20 and all(abs(centre) < .5 for centre in centres)
        assert [error for page in pdf if not inserted(page) for error in outside_body(page)] == []
        page = next(p for p in pdf if "車横最大" in p.get_text() and "縁応力度" in p.get_text())
        top = next(span for span in found if span.text == "安全性" and span.page == page.number + 1).baseline - 25
        rows = [2, 1, 3, 1] + [1] * len(transverse_chain("curve")[2].define_cases)
        assert band_errors(row_bands(page, column_x(10) + 8, top)[:len(rows) + 1], rows) == []
        assert all(measure.monochrome_errors(p) == [] for p in pdf)
