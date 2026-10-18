"""0720 PDF: the drawn text is the manuscript, bytes are deterministic, appearance meets the reference,
and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import json
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
from frame_report_pdf_checks import table_checks
from pdf_handcheck import formula_checks
from test_longitudinal_report_pdf import ANCHOR, APPEARANCE, PAGE_NUMBER, ROOT, _samples, measure, squeeze
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


def test_typography_matches_the_independent_reference_roles(tmp_path: Path):
    roles = json.loads(APPEARANCE.read_text(encoding="utf-8"))["roles"]
    with pymupdf.open(render("pedestal", tmp_path / "0720.pdf")) as pdf:
        samples = _samples(pdf)

        def first(text: str):
            found = [s for s in samples if s.text == text]
            assert found, text
            return found[0]

        for role, text in (("common.chapter", "§11. 線路直角方向の計算（地震時）"), ("common.section", "11.1 検討モデル"),
                           ("common.subsection", "(6) 地震時桁荷重慣性力"), ("common.subsubsection", "1) 柱下端の微小部材")):
            assert measure.role_errors(first(text), roles[role], anchor_x=ANCHOR) == [], role
        assert measure.role_errors(first("荷重種別"), roles["common.table_header"]) == []
        assert measure.role_errors(first("0.010"), roles["frame.dimension"]) == []
        assert all(measure.monochrome_errors(p) == [] for p in pdf)
