"""0610 PDF: the drawn text is the manuscript, bytes are deterministic, appearance meets the reference,
and every printed formula and table row recomputes from the printed numbers."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from gridlayoutpdf import Text

from frame_report_cases import CASES, chain
from frame_report_pdf_checks import table_checks
from pdf_handcheck import formula_checks
from webpier.core.printed import Printed
from webpier.reporting.stages.longitudinal import FOOTER, build_longitudinal, render_longitudinal, semantic_records

ROOT = Path(__file__).parents[2]
APPEARANCE = ROOT / "tests" / "fixtures" / "reporting" / "appearance" / "reference-style.json"
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure", ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

FOOTER_PREFIX = FOOTER.split("{")[0]
ANCHOR = 58.92  # the chapter start of 0600 and later (reporting-style.md)


def squeeze(value: str) -> str:
    return re.sub(r"\s+", "", value)


def render(case: str, path: Path) -> Path:
    pier, reaction, result, _ = chain(case)
    return render_longitudinal(result, reaction, pier, path)


@pytest.mark.parametrize("case", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, case: str):
    pier, reaction, result, _ = chain(case)
    pages = build_longitudinal(result, reaction, pier).layout()
    drawn = [c.text for page in pages for c in page.commands
             if isinstance(c, Text) and not c.text.startswith(FOOTER_PREFIX)]
    assert squeeze("".join(drawn)) == squeeze("".join(r["text"] for r in semantic_records(result, reaction, pier)))
    with pymupdf.open(render(case, tmp_path / "0610.pdf")) as pdf:
        assert len(pdf) == len(pages)
        for number, (page, scene) in enumerate(zip(pdf, pages), 1):
            scene_text = "".join(c.text for c in scene.commands if isinstance(c, Text))
            assert Counter(squeeze(page.get_text())) == Counter(squeeze(scene_text))
            assert f"8 - {number}" in page.get_text()
            assert not page.get_images()


@pytest.mark.parametrize("case", list(CASES))
def test_every_printed_formula_and_table_row_recomputes_from_the_printed_numbers(tmp_path: Path, case: str):
    path = render(case, tmp_path / "0610.pdf")
    formulas = formula_checks(path)
    assert len(formulas) >= 13
    assert [check for check in formulas if not check.ok] == []
    rows = table_checks(path)
    kinds = Counter(check.kind for check in rows)
    # D1, D2, 3 snow, 2 train tables (2 or 3 rows each) and 4 impact tables of 2 rows; 11 totals; 8 horizontal.
    assert kinds["total"] == 11 and kinds["horizontal"] == 8 and kinds["row"] >= 23
    assert [check for check in rows if not check.ok] == []


def test_a_wrong_printed_number_is_caught_by_the_hand_check(tmp_path: Path):
    pier, reaction, result, _ = chain("current")
    table = result.snow[0]
    wrong = replace(table, rows=(replace(table.rows[0], m=Printed(table.rows[0].m.value + 0.01, 2, "kN m")),
                                 *table.rows[1:]))
    path = render_longitudinal(replace(result, snow=(wrong, *result.snow[1:])), reaction, pier, tmp_path / "w.pdf")
    bad = [check for check in table_checks(path) if not check.ok]
    assert [check.kind for check in bad] == ["row", "total"]
    fixed = replace(result.fixed, n=Printed(result.fixed.n.value + 0.01, 2, "kN"))
    path = render_longitudinal(replace(result, fixed=fixed), reaction, pier, tmp_path / "f.pdf")
    assert [check.printed for check in formula_checks(path) if not check.ok] == [f"{fixed.n.value:.2f}"]


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render("current", tmp_path / "a.pdf").read_bytes()
    assert render("current", tmp_path / "b.pdf").read_bytes() == first
    assert b"CreationDate" not in first or b"D:20000101000000" in first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from frame_report_cases import chain\n"
              "from webpier.reporting.stages.longitudinal import render_longitudinal\n"
              "pier, reaction, result, _ = chain('current')\n"
              "render_longitudinal(result, reaction, pier, sys.argv[1])\n")
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
        render_longitudinal(huge, reaction, pier, path)
    assert path.read_bytes() == b"previous-published-bytes"


def _samples(pdf) -> list:
    """Spans with the real face name of the subset font (MS-Mincho, MS-Gothic), as in the 0500 test."""
    from reportlab.pdfbase.ttfonts import TTFont

    from webpier.reporting.fonts import load_fonts

    fonts = load_fonts()
    faces = {}
    for name in ("body", "heading"):
        face = fonts.resolve(name)
        faces[face.pdf_name] = TTFont(f"verify-{name}", str(face.path), subfontIndex=face.face_index).face.name.decode("ascii")
    found = []
    for page in pdf:
        for sample in measure.text_samples(page):
            real = next((faces[pdf_name] for pdf_name in faces if len(sample.font) >= 20 and pdf_name.startswith(sample.font)),
                        sample.font)
            found.append(replace(sample, font=real))
    return found


def test_typography_tables_and_figure_match_the_independent_reference_roles(tmp_path: Path):
    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))
    roles = reference["roles"]
    with pymupdf.open(render("current", tmp_path / "0610.pdf")) as pdf:
        samples = _samples(pdf)

        def first(text: str, **where) -> object:
            found = [s for s in samples if s.text == text and all(getattr(s, k) == v for k, v in where.items())]
            assert found, text
            return found[0]

        for role, text in (("common.chapter", "§8. 線路方向の計算（地震時以外）"), ("common.section", "8.1 検討モデル"),
                           ("common.subsection", "(1) 骨組図"), ("common.subsubsection", "1) 柱（はり・ハンチを含む）"),
                           ("common.body", "フーチングはすべて剛域とする．")):
            assert measure.role_errors(first(text), roles[role], anchor_x=ANCHOR) == [], role
        assert measure.role_errors(first("荷重名称"), roles["common.table_header"]) == []
        assert measure.role_errors(first("5740.00"), roles["common.table_value"]) == []
        # The figure: node numbers MS-Gothic 9.9, member numbers 8, dimensions 9.9 (rotated) on page 1.
        page_one = [s for s in samples if s.page == 1]
        node = next(s for s in page_one if s.text == "1" and s.size > 9)
        member = next(s for s in page_one if s.text == "1" and s.size < 9)
        dimension = next(s for s in page_one if s.text == "2.000")
        for sample, role in ((node, "frame.node"), (member, "frame.member"), (dimension, "frame.dimension")):
            assert measure.role_errors(sample, roles[role]) == [], role
        # Result '=' of the action formulas in the 0600 multi-step result column.
        equals = [s for s in samples if s.text == "=" and abs(s.x - 436.44) < 3]
        assert len(equals) >= 10
        assert all(measure.role_errors(s, roles["horizontal.result_equals"], anchor_x=ANCHOR) == [] for s in equals)
        # R with its subscript B on the baseline of the numbers of its row.
        chars = [(c["c"], c["origin"], span["size"]) for block in pdf[2].get_text("rawdict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"] for c in span["chars"]
                 if not c["c"].isspace()]
        index = next(i for i, (c, _, size) in enumerate(chars) if c == "R" and size > 9 and chars[i + 1][0] == "B")
        (_, main, _), (_, subscript, size) = chars[index], chars[index + 1]
        assert size == pytest.approx(6.5, abs=.1)
        assert subscript[1] - main[1] == pytest.approx(roles["common.subscript"]["baseline_delta_pt"], abs=.06)
        number = next(origin for c, origin, size in chars if c == "5" and size > 9)
        assert number[1] == pytest.approx(main[1], abs=.01)  # the label and the numbers of a row share a baseline
        # The combination table: four header bands, then 20 rows of 14.28 pt (longitudinal.combination).
        contract = reference["tables"]["longitudinal.combination"]
        page = next(p for p in pdf if "変動荷重" in p.get_text() and "地盤の安定" in p.get_text())
        rules = measure.native_rules(page)
        top = next(s for s in samples if s.text == "安全性" and s.page == page.number + 1).baseline - 25
        bands = [b for b in measure.painted_rule_bands(rules, axis="h", crossing=230) if b.coordinate > top][:25]
        heights = [28.56, 14.28, 47.76, 14.28] + [contract["nominal_row_height_pt"]] * 20
        assert measure.table_errors([b.coordinate for b in bands], heights) == []
        assert bands[0].width == pytest.approx(contract["thick_rule_pt"], abs=.001)
        assert bands[-1].width == pytest.approx(contract["thick_rule_pt"], abs=.001)
        assert all(measure.monochrome_errors(p) == [] for p in pdf)


def test_headings_stay_with_what_follows_and_tables_are_not_split():
    pier, reaction, result, _ = chain("pedestal")
    pages = build_longitudinal(result, reaction, pier).layout()
    owners: dict[str, set[int]] = {}
    for number, page in enumerate(pages, 1):
        for placement in page.metadata["placements"]:
            owners.setdefault(placement["block_id"], set()).add(number)
    from webpier.reporting.stages.longitudinal import content

    units = content(result, reaction, pier)
    for index, unit in enumerate(units):
        if unit.kind in ("table", "figure", "diagram"):
            assert len(owners[unit.key]) == 1, unit.key
        if unit.kind == "heading" and index + 1 < len(units) and units[index + 1].key in owners:
            assert max(owners[unit.key]) <= min(owners[units[index + 1].key]), unit.key
