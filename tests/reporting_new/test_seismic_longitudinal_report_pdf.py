"""0710 PDF: the drawn text is the manuscript, bytes are deterministic, appearance meets the reference,
and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Circle, Text

from frame_report_cases import CASES, chain
from frame_report_pdf_checks import table_checks
from pdf_handcheck import formula_checks
from test_longitudinal_report_pdf import ANCHOR, APPEARANCE, ROOT, _samples, measure, squeeze
from webpier.core.printed import Printed
from webpier.reporting.stages.seismic_longitudinal import (
    FOOTER, build_seismic_longitudinal, render_seismic_longitudinal, semantic_records,
)

FOOTER_PREFIX = FOOTER.split("{")[0]


def render(case: str, path: Path) -> Path:
    pier, _, _, result = chain(case)
    return render_seismic_longitudinal(result, pier, path)


@pytest.mark.parametrize("case", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, _, _, result = chain(case)
    pages = build_seismic_longitudinal(result, pier).layout()
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text) and not c.text.startswith(FOOTER_PREFIX)]
    assert squeeze("".join(drawn)) == squeeze("".join(r["text"] for r in semantic_records(result, pier)))
    with pymupdf.open(render(case, tmp_path / "0710.pdf")) as pdf:
        assert len(pdf) == len(pages)
        for number, (page, scene) in enumerate(zip(pdf, pages), 1):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert f"10 - {number}" in page.get_text()
            assert not page.get_images()
    # The micro member is marked on the model figure (Example2 10-1 ◎).
    rings = [c for c in pages[0].commands if isinstance(c, Circle) and c.fill is None]
    assert len(rings) == 1


@pytest.mark.parametrize("case", list(CASES))
def test_every_printed_formula_and_table_row_recomputes_from_the_printed_numbers(tmp_path: Path, case: str):
    path = render(case, tmp_path / "0710.pdf")
    formulas = formula_checks(path)
    pier, _, _, result = chain(case)
    # A, I, four or five Hw, the footing H, and the seat moment with a pedestal.
    assert len(formulas) >= 6
    assert [check for check in formulas if not check.ok] == []
    rows = table_checks(path)
    assert Counter(check.kind for check in rows) == {"row": 2, "total": 1, "horizontal": 2}
    assert [check for check in rows if not check.ok] == []


def test_a_wrong_printed_number_is_caught_by_the_hand_check(tmp_path: Path):
    pier, _, _, result = chain("current")
    inertia = replace(result.self_weight, column=replace(result.self_weight.column, value=Printed(297.67, 2, "kN/m")))
    path = render_seismic_longitudinal(replace(result, self_weight=inertia), pier, tmp_path / "w.pdf")
    assert [check.printed for check in formula_checks(path) if not check.ok] == ["297.67"]


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import chain\n"
              "from webpier.reporting.stages.seismic_longitudinal import render_seismic_longitudinal\n"
              "pier, _, _, result = chain('current')\n"
              "render_seismic_longitudinal(result, pier, sys.argv[1])\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render("asymmetric", tmp_path / "d.pdf").read_bytes() != first


def test_typography_and_tables_match_the_independent_reference_roles(tmp_path: Path):
    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))
    roles = reference["roles"]
    with pymupdf.open(render("pedestal", tmp_path / "0710.pdf")) as pdf:
        samples = _samples(pdf)

        def first(text: str):
            found = [s for s in samples if s.text == text]
            assert found, text
            return found[0]

        for role, text in (("common.chapter", "§10. 線路方向の計算（地震時）"), ("common.section", "10.1 検討モデル"),
                           ("common.subsection", "(3) 自重による地震時慣性力"),
                           ("common.subsubsection", "1) 柱下端の微小部材"),
                           ("common.body", "柱下端の微小部材以外の部材はすべて剛域とする．")):
            assert measure.role_errors(first(text), roles[role], anchor_x=ANCHOR) == [], role
        assert measure.role_errors(first("荷重種別"), roles["common.table_header"]) == []
        page_one = [s for s in samples if s.page == 1]
        assert measure.role_errors(next(s for s in page_one if s.text == "4" and s.size > 9), roles["frame.node"]) == []
        assert measure.role_errors(next(s for s in page_one if s.text == "4" and s.size < 9), roles["frame.member"]) == []
        assert measure.role_errors(first("0.010"), roles["frame.dimension"]) == []
        equals = [s for s in samples if s.text == "=" and abs(s.x - 436.44) < 3]
        assert len(equals) >= 7
        assert all(measure.role_errors(s, roles["horizontal.result_equals"], anchor_x=ANCHOR) == [] for s in equals)
        assert all(measure.monochrome_errors(p) == [] for p in pdf)
