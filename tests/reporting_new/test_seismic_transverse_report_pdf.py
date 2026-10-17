"""0720 PDF: the drawn text is the manuscript, bytes are deterministic, appearance meets the reference,
and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Circle, Text

from frame_report_cases import TRANSVERSE_CASES, transverse_chain
from frame_report_pdf_checks import table_checks
from pdf_handcheck import formula_checks, read_lines, tokens_text
from test_longitudinal_report_pdf import ANCHOR, APPEARANCE, ROOT, _samples, measure, squeeze
from webpier.reporting.stages.seismic_transverse import (
    FOOTER, build_seismic_transverse, render_seismic_transverse, semantic_records,
)

FOOTER_PREFIX = FOOTER.split("{")[0]


def render(case: str, path: Path) -> Path:
    pier, _, _, result = transverse_chain(case)
    return render_seismic_transverse(result, pier, path)


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, _, _, result = transverse_chain(case)
    pages = build_seismic_transverse(result, pier).layout()
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text) and not c.text.startswith(FOOTER_PREFIX)]
    assert squeeze("".join(drawn)) == squeeze("".join(r["text"] for r in semantic_records(result, pier)))
    with pymupdf.open(render(case, tmp_path / "0720.pdf")) as pdf:
        assert len(pdf) == len(pages)
        for number, (page, scene) in enumerate(zip(pdf, pages), 1):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert f"11 - {number}" in page.get_text()
    assert len([c for c in pages[0].commands if isinstance(c, Circle) and c.fill is None]) == 1


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_every_printed_formula_and_table_row_recomputes_from_the_printed_numbers(tmp_path: Path, case: str):
    path = render(case, tmp_path / "0720.pdf")
    formulas = formula_checks(path)
    assert len(formulas) >= 8
    assert [check for check in formulas if not check.ok] == []
    rows = table_checks(path)
    assert Counter(check.kind for check in rows) == {"row": 16, "total": 4}
    assert [check for check in rows if not check.ok] == []


def test_horizontal_forces_print_as_magnitude_and_direction_and_match_their_tables(tmp_path: Path):
    with pymupdf.open(render("current", tmp_path / "0720.pdf")) as pdf:
        lines = [tokens_text(tokens) for page in pdf for _, tokens in read_lines(page)]
    directed = [m for line in lines if (m := re.fullmatch(r"(H|Hw\d)=(\d+\.\d{2})kN(?:/m)?（(←|→)）", line))]
    assert [m[3] for m in directed] == ["→"] * len(directed) and len(directed) == 6
    totals = [m[1] for line in lines if (m := re.fullmatch(r"水平力H=.*=(\d+\.\d{2})kN", line))]
    assert [m[2] for m in directed[:2]] == totals[:2]  # Case 7 and 8 are the totals of (6) and (7)


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import transverse_chain\n"
              "from webpier.reporting.stages.seismic_transverse import render_seismic_transverse\n"
              "pier, _, _, result = transverse_chain('current')\n"
              "render_seismic_transverse(result, pier, sys.argv[1])\n")
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
