"""0620 PDF: the drawn text is the manuscript, bytes are deterministic, appearance meets the reference,
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
from gridlayoutpdf import Text

from frame_report_cases import TRANSVERSE_CASES, transverse_chain
from frame_report_pdf_checks import table_checks
from pdf_handcheck import formula_checks
from test_longitudinal_report_pdf import ANCHOR, APPEARANCE, PAGE_NUMBER, ROOT, _samples, measure, squeeze
from webpier.core.printed import Printed
from load_diagram_support import LOAD_DIAGRAM, PAGES, inserted, layout
from webpier.reporting.stages.transverse import PREFIX, content, render_transverse, semantic_records


def render(case: str, path: Path) -> Path:
    pier, reaction, result, _ = transverse_chain(case)
    return render_transverse(result, reaction, pier, path, LOAD_DIAGRAM)


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, reaction, result, _ = transverse_chain(case)
    before, after = layout(content(result, reaction, pier), PREFIX)
    pages = before + after
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text)]
    assert squeeze("".join(drawn)) == squeeze("".join(r["text"] for r in semantic_records(result, reaction, pier)))
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
    # D1, D2, 3 snow, 3 train, 6 impact tables, 2 wind tables (+3 centrifugal on a curve)
    pier, _, result, _ = transverse_chain(case)
    assert kinds["total"] == 16 + (3 if result.centrifugal is not None else 0)
    assert kinds["row"] >= 80
    assert [check for check in rows if not check.ok] == []


def test_a_wrong_printed_number_is_caught_by_the_hand_check(tmp_path: Path):
    pier, reaction, result, _ = transverse_chain("current")
    table = result.train.up
    wrong = replace(table, rows=(replace(table.rows[0], n=Printed(table.rows[0].n.value + .01, 2, "kN")),
                                 *table.rows[1:]))
    path = render_transverse(replace(result, train=replace(result.train, up=wrong)), reaction, pier, tmp_path / "w.pdf",
                             LOAD_DIAGRAM)
    assert [check.kind for check in table_checks(path) if not check.ok] == ["row", "total"]


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import transverse_chain\n"
              "from load_diagram_support import LOAD_DIAGRAM\n"
              "from webpier.reporting.stages.transverse import render_transverse\n"
              "pier, reaction, result, _ = transverse_chain('current')\n"
              "render_transverse(result, reaction, pier, sys.argv[1], LOAD_DIAGRAM)\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render("curve", tmp_path / "d.pdf").read_bytes() != first


def test_typography_tables_and_figure_match_the_independent_reference_roles(tmp_path: Path):
    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))
    roles = reference["roles"]
    with pymupdf.open(render("curve", tmp_path / "0620.pdf")) as pdf:
        samples = _samples(pdf)

        def first(text: str):
            found = [s for s in samples if s.text == text]
            assert found, text
            return found[0]

        for role, text in (("common.chapter", "§9. 線路直角方向の計算（地震時以外）"), ("common.section", "9.2 作用の計算"),
                           ("common.subsection", "(8) 風荷重"), ("common.subsubsection", "1) 列車荷重がある場合"),
                           ("common.body", "鉛直力は列車荷重に桁の衝撃係数を乗じた値とする．")):
            assert measure.role_errors(first(text), roles[role], anchor_x=ANCHOR) == [], role
        page_one = [s for s in samples if s.page == 1]
        assert measure.role_errors(next(s for s in page_one if s.text == "1" and s.size > 9), roles["frame.node"]) == []
        assert measure.role_errors(next(s for s in page_one if s.text == "1" and s.size < 9), roles["frame.member"]) == []
        assert measure.role_errors(first("4.900"), roles["frame.dimension"]) == []
        equals = [s for s in samples if s.text == "=" and abs(s.x - 436.44) < 3]
        assert len(equals) >= 20
        assert all(measure.role_errors(s, roles["horizontal.result_equals"], anchor_x=ANCHOR) == [] for s in equals)
        # The combination table: four header bands, then the 17 Define rows (on a curve) of 14.28 pt, the rows of
        # longitudinal.combination; this table has the Define cases as rows, as 0610 has its basic cases.
        contract = reference["tables"]["longitudinal.combination"]
        page = next(p for p in pdf if "車横最大" in p.get_text() and "地盤の安定" in p.get_text())
        rules = measure.native_rules(page)
        top = next(s for s in samples if s.text == "安全性" and s.page == page.number + 1).baseline - 25
        bands = [b for b in measure.painted_rule_bands(rules, axis="h", crossing=230) if b.coordinate > top][:22]
        heights = [28.56, 14.28, 47.76, 14.28] + [contract["nominal_row_height_pt"]] * 17
        assert measure.table_errors([b.coordinate for b in bands], heights) == []
        assert all(measure.monochrome_errors(p) == [] for p in pdf)
