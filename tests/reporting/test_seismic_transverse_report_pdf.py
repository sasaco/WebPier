"""0720 PDF: the drawn text is the manuscript, bytes are deterministic, the pages follow the common grid,
and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Circle, Text

from frame_report_cases import TRANSVERSE_CASES, transverse_chain
from jrsnap_pages_support import (
    DATA_CHECK_PAGES, TRANSVERSE_LOAD_CASES, data_check_page, inserted, layout, load_diagram_page,
    page_order, pages as stand_ins,
)
from frame_report_pdf_checks import (
    BODY, HEADING, first, outside_body, placement_errors, row_offset, spans, table_checks,
)
from pdf_handcheck import formula_checks
from test_longitudinal_report_pdf import PAGE_NUMBER, ROOT, measure, squeeze
from webpier.reporting.stages.seismic_transverse import (
    INSERTIONS, content, render_seismic_transverse, semantic_records,
)

REPORT = stand_ins(TRANSVERSE_LOAD_CASES)


def render(case: str, path: Path) -> Path:
    pier, _, _, result = transverse_chain(case)
    return render_seismic_transverse(result, pier, path, REPORT)


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, _, _, result = transverse_chain(case)
    model, actions, combinations = layout(content(result, pier), INSERTIONS)
    pages = model + actions + combinations
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text)]
    assert squeeze("".join(drawn)) == squeeze("".join(r["text"] for r in semantic_records(result, pier)))
    with pymupdf.open(render(case, tmp_path / "0720.pdf")) as pdf:
        # Decisions 50, 51: JRSNAP's データ確認図 pages come right after 11.1 and its load diagram after 11.3.
        assert len(pdf) == len(pages) + DATA_CHECK_PAGES + TRANSVERSE_LOAD_CASES
        assert [data_check_page(page) for page in pdf] == (
            [False] * len(model) + [True] * DATA_CHECK_PAGES
            + [False] * (len(actions) + TRANSVERSE_LOAD_CASES + len(combinations)))
        assert [load_diagram_page(page) for page in pdf] == (
            [False] * (len(model) + DATA_CHECK_PAGES + len(actions)) + [True] * TRANSVERSE_LOAD_CASES
            + [False] * len(combinations))
        for page, scene in zip([page for page in pdf if not inserted(page)], pages):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert not PAGE_NUMBER.search(page.get_text())
    assert len([c for c in pages[0].commands if isinstance(c, Circle) and c.fill is None]) == 1


def test_the_pages_are_the_model_the_data_check_the_actions_the_load_diagram_and_the_combinations(tmp_path: Path):
    page_order(render("current", tmp_path / "0720.pdf"), 11, TRANSVERSE_LOAD_CASES)


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_every_printed_formula_and_table_row_recomputes_from_the_printed_numbers(tmp_path: Path, case: str):
    path = render(case, tmp_path / "0720.pdf")
    formulas = formula_checks(path)
    assert len(formulas) >= 8
    assert [check for check in formulas if not check.ok] == []
    rows = table_checks(path)
    assert Counter(check.kind for check in rows) == {"row": 16, "total": 4}
    assert [check for check in rows if not check.ok] == []


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import transverse_chain\n"
              "from jrsnap_pages_support import TRANSVERSE_LOAD_CASES, pages\n"
              "from webpier.reporting.stages.seismic_transverse import render_seismic_transverse\n"
              "pier, _, _, result = transverse_chain('current')\n"
              "render_seismic_transverse(result, pier, sys.argv[1], pages(TRANSVERSE_LOAD_CASES))\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first


def test_the_pages_follow_the_grid_contract(tmp_path: Path):
    """As 0610 (test_longitudinal_report_pdf): the heading columns and faces, the table and figure faces and
    nothing beyond the body."""
    with pymupdf.open(render("pedestal", tmp_path / "0720.pdf")) as pdf:
        found = spans(pdf)
        placed = (("§11. 線路直角方向の計算（地震時）", 0, HEADING), ("11.1 検討モデル", 1, HEADING),
                  ("(6) 地震時桁荷重慣性力", 2, HEADING), ("1) 柱下端の微小部材", 3, HEADING))
        assert [error for text, column, face in placed for error in placement_errors(first(found, text), column, face)] == []
        assert len({round(row_offset(first(found, text)), 2) for text, *_ in placed}) == 1
        assert (first(found, "荷重種別").face, first(found, "荷重種別").size) == (BODY, 10.0)
        dimension = first(found, "0.010")
        assert (dimension.face, dimension.size, dimension.upright) == (HEADING, 10.0, False)
        assert [error for page in pdf if "FAKE" not in page.get_text() for error in outside_body(page)] == []
        assert all(measure.monochrome_errors(p) == [] for p in pdf)
