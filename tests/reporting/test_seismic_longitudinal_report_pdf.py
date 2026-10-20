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
from jrsnap_pages_support import (
    DATA_CHECK_PAGES, LONGITUDINAL_LOAD_CASES, data_check_page, inserted, layout, load_diagram_page,
    page_order, pages as stand_ins,
)
from frame_report_pdf_checks import table_checks
from pdf_handcheck import formula_checks
from test_longitudinal_report_pdf import ANCHOR, APPEARANCE, PAGE_NUMBER, ROOT, _samples, measure, squeeze
from webpier.core.printed import Printed
from webpier.reporting.stages.seismic_longitudinal import (
    INSERTIONS, content, render_seismic_longitudinal, semantic_records,
)

REPORT = stand_ins(LONGITUDINAL_LOAD_CASES)


def render(case: str, path: Path) -> Path:
    pier, _, _, result = chain(case)
    return render_seismic_longitudinal(result, pier, path, REPORT)


@pytest.mark.parametrize("case", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, _, _, result = chain(case)
    model, actions, combinations = layout(content(result, pier), INSERTIONS)
    pages = model + actions + combinations
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text)]
    assert squeeze("".join(drawn)) == squeeze("".join(r["text"] for r in semantic_records(result, pier)))
    with pymupdf.open(render(case, tmp_path / "0710.pdf")) as pdf:
        # Decisions 50, 51: JRSNAP's データ確認図 pages come right after 10.1 and its load diagram after 10.3.
        assert len(pdf) == len(pages) + DATA_CHECK_PAGES + LONGITUDINAL_LOAD_CASES
        assert [data_check_page(page) for page in pdf] == (
            [False] * len(model) + [True] * DATA_CHECK_PAGES
            + [False] * (len(actions) + LONGITUDINAL_LOAD_CASES + len(combinations)))
        assert [load_diagram_page(page) for page in pdf] == (
            [False] * (len(model) + DATA_CHECK_PAGES + len(actions)) + [True] * LONGITUDINAL_LOAD_CASES
            + [False] * len(combinations))
        for page, scene in zip([page for page in pdf if not inserted(page)], pages):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert not PAGE_NUMBER.search(page.get_text())
            assert not page.get_images()
    # The micro member is marked on the model figure (Example2 10-1 ◎).
    rings = [c for c in pages[0].commands if isinstance(c, Circle) and c.fill is None]
    assert len(rings) == 1


def test_the_pages_are_the_model_the_data_check_the_actions_the_load_diagram_and_the_combinations(tmp_path: Path):
    page_order(render("current", tmp_path / "0710.pdf"), 10, LONGITUDINAL_LOAD_CASES)


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
    path = render_seismic_longitudinal(replace(result, self_weight=inertia), pier, tmp_path / "w.pdf",
                                       REPORT)
    assert [check.printed for check in formula_checks(path) if not check.ok] == ["297.67"]


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import chain\n"
              "from jrsnap_pages_support import LONGITUDINAL_LOAD_CASES, pages\n"
              "from webpier.reporting.stages.seismic_longitudinal import render_seismic_longitudinal\n"
              "pier, _, _, result = chain('current')\n"
              "render_seismic_longitudinal(result, pier, sys.argv[1], pages(LONGITUDINAL_LOAD_CASES))\n")
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


def test_the_displaced_soil_of_several_layers_prints_its_average(tmp_path: Path):
    # decision 64: H5 + H6 = 2.700 spans 支持層 (0–2.650, 19.0) and ローム (2.650–2.700, 17.0):
    # γ' = (0.050 × 17.0 + 2.650 × 19.0) / 2.700 = 18.962… → 19.0
    from copy import deepcopy

    from frame_report_cases import CURRENT
    from webpier.calc.foundation import calculate_foundation
    from webpier.calc.longitudinal import calculate_longitudinal
    from webpier.calc.reaction import calculate_reaction
    from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
    from webpier.inputs import parse_input

    data = deepcopy(CURRENT)
    layers = data["地盤データ"]["層"]
    layers[0]["層厚"] = 1.05
    layers.insert(1, deepcopy(layers[0]) | {"層番": "ローム", "層厚": 1.0, "土質区分": "粘性土",
                                           "単位体積重量": {"湿潤": 17.0, "水中": 7.0}})
    data["下部構造"]["単位体積重量"]["フーチング"] = 24.5
    pier = parse_input(data)
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    result = calculate_seismic_longitudinal(pier, foundation, reaction,
                                            calculate_longitudinal(pier, foundation, reaction))
    assert result.self_weight.footing.displaced == Printed(19.0, 1, "kN/m3")
    text = "".join(squeeze(r["text"]) for r in semantic_records(result, pier))
    assert "γ'=(0.050×17.0+2.650×19.0)/2.700=19.0" in text and "厚さによる平均" in text
    checks = formula_checks(render_seismic_longitudinal(result, pier, tmp_path / "layers.pdf", REPORT))
    assert [check for check in checks if not check.ok] == []
