"""0610 PDF: the drawn text is the manuscript, bytes are deterministic, the pages follow the common grid (GridLayoutPdf
0.2.0), and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Text

from frame_report_cases import CASES, chain, dead_tables
from frame_report_pdf_checks import (
    BODY, HEADING, band_errors, column_x, drawn_order_errors, first, outside_body, placement_errors, relation_centres, row_bands, row_offset,
    spans, table_checks,
)
from pdf_handcheck import formula_checks
from webpier.core.printed import Printed
from load_diagram_support import PAGES, REPORT, inserted, layout
from webpier.reporting.stages.longitudinal import (
    PREFIX, build_longitudinal, content, render_longitudinal, semantic_records,
)

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure", ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

PAGE_NUMBER = re.compile(r"^\d+ - \d+$", re.MULTILINE)  # the reference prints no page numbers


def squeeze(value: str) -> str:
    return re.sub(r"\s+", "", value)


def render(case: str, path: Path) -> Path:
    pier, reaction, result, _ = chain(case)
    return render_longitudinal(result, reaction, pier, path, REPORT)


@pytest.mark.parametrize("case", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, reaction, result, _ = chain(case)
    before, after = layout(content(result, reaction, pier), PREFIX)
    pages = before + after
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text)]
    assert drawn_order_errors(squeeze("".join(drawn)), content(result, reaction, pier)) == []
    with pymupdf.open(render(case, tmp_path / "0610.pdf")) as pdf:
        # Decision 44: the load diagram pages come right after 8.3, and 8.4 starts the next page.
        assert len(pdf) == len(pages) + PAGES
        assert [inserted(page) for page in pdf] == [False] * len(before) + [True] * PAGES + [False] * len(after)
        assert "8.3 荷重図" in pdf[len(before) - 1].get_text()
        assert pdf[len(before) + PAGES].get_text().lstrip().startswith("8.4 設計作用の組合せ")
        for page, scene in zip([page for page in pdf if not inserted(page)], pages):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert not PAGE_NUMBER.search(page.get_text())
            assert not page.get_images()


@pytest.mark.parametrize("case", list(CASES))
def test_every_printed_formula_and_table_row_recomputes_from_the_printed_numbers(tmp_path: Path, case: str):
    path = render(case, tmp_path / "0610.pdf")
    formulas = formula_checks(path)
    assert len(formulas) >= 15  # the buoyancy lines with negative results count too
    assert [check for check in formulas if not check.ok] == []
    rows = table_checks(path)
    kinds = Counter(check.kind for check in rows)
    # D1, D2, 3 snow, the double-track train table (2 or 3 rows) and 2 impact tables of 2 rows each placing; 10
    # horizontal. Decision 120 (g): no single-track train or impact table. Without snow, no snow table (decision 69);
    # with girders on the pedestal, D1 at its top too (decision 81).
    result = chain(case)[2]
    snow = 3 if result.snow is not None else 0
    # the train and impact tables of ①, ② and ③, and the bearing forces of ① and the seven with the train of ② and ③
    # (decisions 102, 120: the two reduced-dead-load cases)
    assert kinds["total"] == 3 * 3 + len(dead_tables(result)) + snow and kinds["horizontal"] == 10 + 2 * 7
    assert kinds["row"] >= 17 + 2 * snow
    assert [check for check in rows if not check.ok] == []


def test_a_wrong_printed_number_is_caught_by_the_hand_check(tmp_path: Path):
    pier, reaction, result, _ = chain("current")
    table = result.snow[0]
    wrong = replace(table, rows=(replace(table.rows[0], m=Printed(table.rows[0].m.value + 0.01, 2, "kN m")),
                                 *table.rows[1:]))
    path = render_longitudinal(replace(result, snow=(wrong, *result.snow[1:])), reaction, pier, tmp_path / "w.pdf",
                               REPORT)
    bad = [check for check in table_checks(path) if not check.ok]
    assert [check.kind for check in bad] == ["row", "total"]
    fixed = replace(result.fixed, n=Printed(result.fixed.n.value + 0.01, 2, "kN"))
    path = render_longitudinal(replace(result, fixed=fixed), reaction, pier, tmp_path / "f.pdf", REPORT)
    assert [check.printed for check in formula_checks(path) if not check.ok] == [f"{fixed.n.value:.2f}"]


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    assert b"CreationDate" not in first or b"D:20000101000000" in first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import chain\n"
              "from load_diagram_support import REPORT\n"
              "from webpier.reporting.stages.longitudinal import render_longitudinal\n"
              "pier, reaction, result, _ = chain('current')\n"
              "render_longitudinal(result, reaction, pier, sys.argv[1], REPORT)\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render("pedestal", tmp_path / "d.pdf").read_bytes() != first


def test_render_replaces_the_target_only_after_a_complete_layout(tmp_path: Path):
    from gridlayoutpdf import LayoutError

    pier, reaction, result, _ = chain("current")
    huge = replace(result, fixed=replace(result.fixed, n=Printed(1e40, 2, "kN")))
    path = tmp_path / "previous.pdf"
    path.write_bytes(b"previous-published-bytes")
    with pytest.raises(LayoutError):
        render_longitudinal(huge, reaction, pier, path, REPORT)
    assert path.read_bytes() == b"previous-published-bytes"


def subscript_errors(pdf) -> list[str]:
    """R with its 6.5 pt subscript B 1.92 pt below the line (Example2's subscripts) on the baseline of the numbers of
    its table row."""
    for page in pdf:
        chars = [(c["c"], c["origin"], span["size"]) for block in page.get_text("rawdict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"] for c in span["chars"]
                 if not c["c"].isspace()]
        index = next((i for i, (c, _, size) in enumerate(chars[:-1]) if c == "R" and size > 9 and chars[i + 1][0] == "B"),
                     None)
        if index is None:
            continue
        (_, main, _), (_, subscript, size) = chars[index], chars[index + 1]
        number = next(origin for c, origin, size in chars[index:] if c.isdigit() and size > 9)
        return [error for error, ok in (
            (f"subscript size {size}", abs(size - 6.5) < .1),
            (f"subscript drop {subscript[1] - main[1]:.2f}", abs(subscript[1] - main[1] - 1.92) < .06),
            (f"row baseline {number[1]:.2f} != {main[1]:.2f}", abs(number[1] - main[1]) < .01)) if not ok]
    return ["no R_B"]


def test_the_pages_follow_the_grid_contract(tmp_path: Path):
    """Headings at their level's column in MS Gothic 10 pt and the body from column 4 in MS Mincho 10 pt, each line on
    a grid row; the figure's numbers and dimensions; the result "=" of the action formulas centred on the boundary
    before column 22; nothing beyond the body's 30 columns; and the coefficient table (8-10) in whole grid rows:
    four header bands of 2, 1, 4 and 1 rows (the remarks with the water level and the placing, decision 120), then a
    row a basic case."""
    with pymupdf.open(render("current", tmp_path / "0610.pdf")) as pdf:
        found = spans(pdf)
        placed = (("§8. 線路方向の計算（地震時以外）", 0, HEADING), ("8.1 検討モデル", 1, HEADING), ("(1) 骨組図", 2, HEADING),
                  ("1) 柱（はり・ハンチを含む）", 3, HEADING), ("フーチングはすべて剛域とする．", 4, BODY))
        assert [error for text, column, face in placed for error in placement_errors(first(found, text), column, face)] == []
        assert len({round(row_offset(first(found, text)), 2) for text, *_ in placed}) == 1
        for text in ("荷重名称", "5740.00"):
            assert (first(found, text).face, first(found, text).size) == (BODY, 10.0), text
        page_one = [span for span in found if span.page == 1]
        assert any(span.text == "1" and (span.face, span.size) == (HEADING, 10.0) for span in page_one)  # a node
        assert any(span.text == "1" and (span.face, span.size) == (HEADING, 8.0) for span in page_one)  # a member
        dimension = first(found, "2.000")
        assert (dimension.face, dimension.size, dimension.upright) == (HEADING, 10.0, False)
        centres = relation_centres(pdf, 22)
        assert len(centres) >= 10 and all(abs(centre) < .5 for centre in centres)
        assert subscript_errors(pdf) == []
        assert [error for page in pdf if not inserted(page) for error in outside_body(page)] == []
        page = next(p for p in pdf if "制動最大" in p.get_text())  # the first part of the table
        top = next(span for span in found if span.text == "安全性" and span.page == page.number + 1).baseline - 25
        rows = [2, 1, 4, 1] + [1] * len(chain("current")[2].basic_cases)
        # the first combination column: after No, 記号 and 荷重名称 of 1, 5 and 5 columns (decision 102)
        assert band_errors(row_bands(page, column_x(11) + 8, top)[:len(rows) + 1], rows) == []
        assert all(measure.monochrome_errors(p) == [] for p in pdf)


def test_the_horizontal_summary_is_split_between_requirement_groups_with_the_header_again(tmp_path: Path):
    """8.2 (7) 1): two grid rows the header and each case, as Example2's. Example2 with ①, ② and ③ (decisions 102,
    120) has 使用性 0.8LR and 1.0LR of ①, ② and ③ (4 cases), 安全性（破壊） 1.0LR + 1.23B, 1.1LR + 1.23B and
    1.0LR + 1.35B of ①, ② and ③, the latter two also with the reduced dead loads, and 1.0LR (5 × 3 + 1 = 16), 復旧性
    1.0LR + B of ①, ② and ③ and 1.0LR (4). 2 + 2 × (4 + 16 + 4) = 50 grid rows do not fit a page of 47, so the table
    is cut between requirement groups: 使用性 and 安全性 (2 + 2 × 20 = 42 rows) on one page, 復旧性 (2 + 2 × 4 = 10) on
    the next, each with the header; no requirement's vertical label is cut."""
    path = render("current", tmp_path / "0610.pdf")
    by_page = Counter(check.page for check in table_checks(path) if check.kind == "horizontal")
    with pymupdf.open(path) as pdf:
        found = spans(pdf)
        header = [page for page in pdf if "荷重種別起点桁(kN)終点桁(kN)合計(kN)" in squeeze(page.get_text())]
        assert len(header) == 2 and header[1].number == header[0].number + 1
        texts = [squeeze(page.get_text()) for page in header]
        assert ["使用性" in t and "安全性（破壊）" in t and "復旧性" not in t for t in texts] == [True, False]
        assert "復旧性" in texts[1] and "安全性（破壊）" not in texts[1]
        assert [by_page[page.number + 1] for page in header] == [4 + 16, 4]
        for page, cases in zip(header, (20, 4)):
            top = next(span for span in found if span.text.startswith("起点桁") and span.page == page.number + 1)
            rows = [2] * (1 + cases)
            # the 起点桁 column: after the requirement and the name of 2 and 12 columns from the table's left edge
            assert band_errors(row_bands(page, column_x(3 + 14) + 8, top.baseline - 25)[:len(rows) + 1], rows) == []


def test_the_reduced_cases_of_the_combination_table_have_their_own_name(tmp_path: Path):
    """8.4 (3): the combination table has no 区分, so the rows of the reduced-dead-load cases (Example2's 25-27 and
    31-33) print "ﾛﾝｸﾞ+制動･低減" in the 荷重名称 of 5 grid columns, in every part of the table, and the note says what
    the 低減 is; the other rows of the same symbols keep "ﾛﾝｸﾞﾚｰﾙ+制動"."""
    path = render("current", tmp_path / "0610.pdf")
    with pymupdf.open(path) as pdf:
        parts = [text for text in (squeeze(page.get_text()) for page in pdf) if text.startswith("No記号荷重名称")]
        assert len(parts) == 6  # 48 combinations, 8 a part
        for text in parts:
            assert text.count("ﾛﾝｸﾞ+制動･低減") == 6
            assert "251.1LR+1.23B-1ﾛﾝｸﾞ+制動･低減" in text and "221.1LR+1.23B-1ﾛﾝｸﾞﾚｰﾙ+制動" in text
            assert "311.0LR+1.35B-1ﾛﾝｸﾞ+制動･低減" in text and "281.0LR+1.35B-1ﾛﾝｸﾞﾚｰﾙ+制動" in text
        assert sum("荷重名称の低減は水平荷重の（死荷重低減あり）を示す．" in squeeze(page.get_text()) for page in pdf) == 1


def test_headings_stay_with_what_follows_and_tables_are_not_split():
    pier, reaction, result, _ = chain("pedestal")
    pages = build_longitudinal(result, reaction, pier).layout()
    owners: dict[str, set[int]] = {}
    for number, page in enumerate(pages, 1):
        for placement in page.metadata["placements"]:
            owners.setdefault(placement["block_id"], set()).add(number)
    from webpier.reporting.stages.frame_report import TableParts
    from webpier.reporting.stages.longitudinal import content

    units = content(result, reaction, pier)
    for index, unit in enumerate(units):
        if isinstance(getattr(unit.value, "block", None), TableParts):  # one page at most a part (8-10, 8.2 (7) 1))
            assert len(owners[unit.key]) <= len(unit.value.block.specs), unit.key
        elif unit.kind in ("table", "figure"):
            assert len(owners[unit.key]) == 1, unit.key
        if unit.kind == "heading" and index + 1 < len(units) and units[index + 1].key in owners:
            assert max(owners[unit.key]) <= min(owners[units[index + 1].key]), unit.key
