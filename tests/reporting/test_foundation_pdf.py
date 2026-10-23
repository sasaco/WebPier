"""0500 PDF: the drawn text is the manuscript, bytes are deterministic, the layout follows the common grid."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from gridlayoutpdf import Equation, Literal, Root, Row, Script, TermStop, Text

from foundation_report_cases import CASES, case
from webpier.inputs.model import Soil
from webpier.reporting.equations import Definition
from webpier.reporting.styles import BODY, HEADING, column_x
from webpier.reporting.stages.foundation import build_foundation, content, render_foundation

ROOT = Path(__file__).parents[2]
APPEARANCE = ROOT / "tests" / "fixtures" / "reporting" / "appearance" / "reference-style.json"
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure", ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

PAGE_NUMBER = re.compile(r"^\d+ - \d+$", re.MULTILINE)  # the reference prints no page numbers


def drawn(value: Any) -> str:
    """What a node draws as text: radicals are strokes and term columns spaces, not characters."""
    if isinstance(value, str):
        return value
    if isinstance(value, TermStop):
        return ""
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(drawn(item) for item in value.items)
    if isinstance(value, Script):
        return drawn(value.base) + drawn(value.subscript or "") + drawn(value.superscript or "")
    if isinstance(value, Root):
        return drawn(value.body)
    if isinstance(value, Equation):
        result = "" if value.result is None else value.result_relation + drawn(value.result)
        return drawn(value.lhs) + value.relation + drawn(value.rhs) + result + drawn(value.unit or "")
    if isinstance(value, Definition):
        result = "" if value.value is None else "(=" + drawn(value.value) + drawn(value.unit or "") + ")"
        return drawn(value.symbol) + "：" + drawn(value.text) + result
    if isinstance(value, tuple):
        return "".join(drawn(item) for item in value)
    raise TypeError(type(value).__name__)


def squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def expected_drawing(result, pier, embedment) -> str:
    parts = []
    for unit in content(result, pier, embedment):
        if unit.key == "soil.header":
            # The second header row (湿潤・水中) is drawn after the first row.
            first = tuple(value if index != 4 else value[0] for index, value in enumerate(unit.value))
            parts.append(drawn(first) + drawn(unit.value[4][1:]))
        else:
            parts.append(unit.lead + drawn(unit.value))
    return squeeze("".join(parts))


def scene_texts(pages) -> list[str]:
    return [command.text for page in pages for command in page.commands
            if isinstance(command, Text)]


@pytest.mark.parametrize("name", list(CASES))
def test_the_scene_draws_every_record_in_order_and_the_pdf_has_the_same_text(tmp_path: Path, name: str):
    result, pier, embedment = case(name)
    document = build_foundation(result, pier, embedment)
    pages = document.layout()
    assert squeeze("".join(scene_texts(pages))) == expected_drawing(result, pier, embedment)
    path = render_foundation(result, pier, embedment, tmp_path / "0500.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(pages)
        for page, scene in zip(pdf, pages):
            pdf_chars = Counter(squeeze(page.get_text()))
            scene_chars = Counter(squeeze("".join(command.text for command in scene.commands if isinstance(command, Text))))
            assert pdf_chars == scene_chars
            assert not PAGE_NUMBER.search(page.get_text())
            assert not page.get_images()


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    first = render_foundation(*case("current"), tmp_path / "a.pdf").read_bytes()
    second = render_foundation(*case("current"), tmp_path / "b.pdf").read_bytes()
    assert first == second
    assert b"CreationDate" not in first or b"D:20000101000000" in first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from foundation_report_cases import case\n"
              "from webpier.reporting.stages.foundation import render_foundation\n"
              "render_foundation(*case('current'), sys.argv[1])\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render_foundation(*case("clay"), tmp_path / "d.pdf").read_bytes() != first


def test_render_replaces_the_target_only_after_a_complete_layout(tmp_path: Path):
    from gridlayoutpdf import LayoutError
    from webpier.core.printed import Printed

    result, pier, embedment = case("current")
    huge = replace(pier.soil.layers[1], deformation_modulus=Printed(1e100, 0, "kN/m2"))
    pier = replace(pier, soil=Soil((pier.soil.layers[0], huge)))
    path = tmp_path / "previous.pdf"
    path.write_bytes(b"previous-published-bytes")
    with pytest.raises(LayoutError):
        render_foundation(result, pier, embedment, path)
    assert path.read_bytes() == b"previous-published-bytes"


def test_a_long_soil_table_keeps_every_row_across_pages(tmp_path: Path):
    result, pier, embedment = case("current")
    template = pier.soil.layers[1]
    layers = (pier.soil.layers[0], *(replace(template, name=f"層{index:03d}") for index in range(60)))
    layers = (*layers[:30], replace(layers[30], soil_type="砂質土と粘性土の互層を含む区分"), *layers[31:])
    path = render_foundation(result, replace(pier, soil=Soil(layers)), embedment, tmp_path / "long.pdf")
    with pymupdf.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf)
        assert len(pdf) > 3
        assert all(text.count(f"層{index:03d}") == 1 for index in range(60))
        assert "砂質土と粘性土の互層を含む区分" in text.replace("\n", "")


def test_long_names_wrap_without_shrinking_and_labels_stay_with_their_equations(tmp_path: Path):
    result, pier, embedment = case("current")
    name, soil_type = "長い地層名称と砂礫を含む地層", "砂質土と粘性土の互層を含む区分"
    surface = replace(pier.soil.layers[0], name=name, soil_type=soil_type)
    path = render_foundation(result, replace(pier, soil=Soil((surface, pier.soil.layers[1]))), embedment, tmp_path / "names.pdf")
    with pymupdf.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf).replace("\n", "")
        assert text.count(name) == 1 and text.count(soil_type) == 1
        for page in pdf:
            body = [line.strip() for line in page.get_text().splitlines()
                    if line.strip()]
            assert body[-1] not in ("・長期", "・短期")
            for direction, label in (("Kr_longitudinal", "線路方向"), ("Kr_transverse", "線路直角方向")):
                if label in page.get_text():
                    # The direction's subsection, Iv to the short-term Kr, is on one page.
                    assert f"{getattr(result.short_term, direction).value:,.0f}" in page.get_text().replace(" ", "")
        spans = [span for page in pdf for block in page.get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"] if span["text"] and span["text"] in name]
        assert spans and all(span["size"] == 10 for span in spans)


HEADING_STARTS = tuple(column_x(column) for column in (0, 1, 2, 3, 18))  # the heading levels and the tag


def _texts(pages) -> list[tuple[int, Text]]:
    return [(number, command) for number, page in enumerate(pages, 1) for command in page.commands
            if isinstance(command, Text) and command.text.strip()]


@pytest.mark.parametrize("name", list(CASES))
def test_every_text_is_ms_mincho_or_ms_gothic_at_10_pt_with_6_5_pt_scripts_on_grid_rows(name: str):
    """No text is shrunk or stretched: the body MS明朝, headings and the soil table MSゴシック, all 10 pt; scripts
    6.5 pt. Every 10 pt line stands on its own grid row (one line, one row), the same offset into each row."""
    pages = build_foundation(*case(name)).layout()
    texts = _texts(pages)
    assert {(command.style.font, command.style.size) for _, command in texts} == {
        ("MS Mincho", 10), ("MS Gothic", 10), ("MS Mincho", 6.5), ("MS Gothic", 6.5)}
    assert all(command.style.size in (10, 6.5) for _, command in texts)
    grid = pages[0].profile.grid
    # The flow (body, equations, headings) shares one baseline offset; the soil table centres its cells' lines.
    offsets = {round((command.y - grid.origin_y) % grid.pitch_y, 3) for _, command in texts
               if command.style == BODY
               or (command.style == HEADING and min(abs(command.x - x) for x in HEADING_STARTS) < .01)}
    assert len(offsets) == 1, offsets
    headings = {command.text for _, command in texts if command.style.font == "MS Gothic" and command.style.size == 10}
    assert {"§5. 地盤のモデル化", "5.2 地盤反力係数の算定", "【基礎標準 13.2.2.2】", "層番", "粘着力"} <= headings


def test_headings_body_and_soil_table_stand_on_the_common_grid_columns(tmp_path: Path):
    """§5 from column 0, 5.1 from 1, (1) from 2, 1) from 3, the body from 4 and the source tag from 18 (as the other
    reports); the soil table spans the body's 30 columns at whole-column widths, framed medium with hair rules."""
    from gridlayoutpdf import BorderStyle
    from webpier.reporting.styles import PITCH_Y

    result, pier, embedment = case("current")
    document = build_foundation(result, pier, embedment)
    starts = {command.text: command.x for _, command in _texts(document.layout())}
    for text, column in (("§5. 地盤のモデル化", 0), ("5.1 地盤の諸数値の設計用値のまとめ", 1),
                         ("(1) フーチング底面の鉛直地盤ばね定数", 2), ("1) フーチング底面の鉛直地盤反力係数", 3),
                         ("1) 線路方向", 3), ("本橋脚の設計に用いる地盤の諸数値の設計用値を表 2.4.8 に示す.", 4),
                         ("支持層の支持力係数", 4), ("・長期", 4), ("【基礎標準 13.2.2.2】", 18)):
        assert starts[text] == pytest.approx(column_x(column), abs=.01), text
    path = document.render(tmp_path / "grid.pdf", invariant=True)
    with pymupdf.open(path) as pdf:
        rules = measure.native_rules(pdf[0])
        table = [rule for rule in rules
                 if rule.width in (BorderStyle.HAIR.stroke_width, BorderStyle.MEDIUM.stroke_width)]
        vertical = [rule for rule in table if rule.axis == "v"]
        horizontal = [rule for rule in table if rule.axis == "h"]
        # Column boundaries: 層番 3, 層厚 3, 土質区分 3, Ｎ値 2, 湿潤 3, 水中 3, 内部摩擦角 4, 粘着力 5, 変形係数 4.
        boundaries = (0, 3, 6, 9, 11, 14, 17, 21, 26, 30)
        frame = BorderStyle.MEDIUM.stroke_width / 2  # the frame is drawn inside the table
        assert sorted({round(rule.coordinate, 2) for rule in vertical}) == pytest.approx(
            [column_x(boundaries[0]) + frame, *(column_x(column) for column in boundaries[1:-1]),
             column_x(boundaries[-1]) - frame], abs=.01)
        assert {rule.width for rule in vertical if not column_x(0) + 1 < rule.coordinate < column_x(30) - 1} == {
            BorderStyle.MEDIUM.stroke_width}
        assert {rule.width for rule in vertical if column_x(0) + 1 < rule.coordinate < column_x(30) - 1} == {
            BorderStyle.HAIR.stroke_width}
        rows = sorted({round(rule.coordinate, 2) for rule in horizontal})
        top, bottom = rows[0] - frame, rows[-1] + frame
        assert bottom - top == pytest.approx(PITCH_Y * (2 + len(pier.soil.layers)), abs=.01)
        assert all(((row - top) / PITCH_Y) % 1 in (pytest.approx(0, abs=.01), pytest.approx(1, abs=.01))
                   for row in rows[1:-1])
        assert all(measure.monochrome_errors(page) == [] for page in pdf)


def test_scripts_sit_at_the_measured_offsets_in_the_kv_equations(tmp_path: Path):
    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))["roles"]
    path = render_foundation(*case("current"), tmp_path / "scripts.pdf")
    with pymupdf.open(path) as pdf:
        chars = [(char["c"], char["origin"], span["size"]) for block in pdf[0].get_text("rawdict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"] for char in span["chars"]
                 if not char["c"].isspace()]
    # The first symbolic equation: k with subscript v, ..., B with subscript v and superscript -1/2.
    index = next(index for index, (c, _, size) in enumerate(chars)
                 if c == "k" and size > 8 and chars[index + 1][0] == "v" and chars[index + 1][2] < 8)
    main, subscript = chars[index][1], chars[index + 1][1]
    superscript = next(origin for c, origin, size in chars[index:] if c == "-" and size < 8)
    assert subscript[1] - main[1] == pytest.approx(reference["common.subscript"]["baseline_delta_pt"], abs=.06)
    assert superscript[1] - main[1] == pytest.approx(reference["common.superscript"]["baseline_delta_pt"], abs=.06)


def _rows(page) -> list[list[dict]]:
    """The 10 pt spans of *page* by baseline, left to right (scripts left out)."""
    rows: dict[float, list[dict]] = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["size"] > 8 and span["text"].strip():
                    rows.setdefault(round(span["origin"][1], 2), []).append(span)
    return [sorted(spans, key=lambda span: span["origin"][0]) for _, spans in sorted(rows.items())]


def _centre(span: dict) -> float:
    return (span["bbox"][0] + span["bbox"][2]) / 2


def _substitution_terms(path: Path) -> list[list[dict]]:
    """The right-hand terms of each substitution: between its "=" centred on the boundary before body column 6 and
    its result's "=" centred on the boundary before column 21."""

    found = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            for spans in _rows(page):
                equals = [span for span in spans if span["text"].strip() == "="]
                if (len(equals) >= 2 and abs(_centre(equals[0]) - column_x(6)) < .1
                        and abs(_centre(equals[-1]) - column_x(21)) < .1):
                    found.append([span for span in spans
                                  if equals[0]["bbox"][2] < span["origin"][0] < equals[-1]["origin"][0]])
    return found


@pytest.mark.parametrize("name", list(CASES))
def test_the_terms_of_one_family_stand_in_the_same_columns(tmp_path: Path, name: str):
    """kv, Kv, ks, Ks, Iv and Kr: each number ends, and each operator is centred, in one column for
    the long- and short-term (and both directions') equations, though labels and blank lines part them.
    Each term stands in whole grid columns: a number ends 2.4 pt (Excel's cell padding) before a column boundary."""
    from webpier.reporting.styles import PITCH_X
    from foundation_report_cases import text

    result, pier, embedment = case(name)
    lines = _substitution_terms(render_foundation(result, pier, embedment, tmp_path / "terms.pdf"))
    springs = (result.long_term, result.short_term)
    kv = {text(values.kv) for values in springs}
    inertia = {text(result.inertia_longitudinal), text(result.inertia_transverse)}

    def first(line: list[dict]) -> str:
        return line[0]["text"].strip()

    families = {
        "kv": [line for line in lines if len(line) == 7 and first(line) == text(result.coefficient)],
        "Kv": [line for line in lines if len(line) == 3 and first(line) in kv and line[2]["text"] == text(result.area)],
        "ks": [line for line in lines if first(line) == result.shear_ratio_text],
        "Ks": [line for line in lines if len(line) == 3 and first(line) in {text(values.ks) for values in springs}
               and line[2]["text"] == text(result.area)],
        "Iv": [line for line in lines if len(line) == 5 and line[-1]["text"] == "12"],
        "Kr": [line for line in lines if len(line) == 3 and first(line) in kv and line[2]["text"] in inertia],
    }
    assert {family: len(found) for family, found in families.items()} == {
        "kv": 2, "Kv": 2, "ks": 2, "Ks": 2, "Iv": 2, "Kr": 4}
    for family, found in families.items():
        for column in range(len(found[0])):
            spans = [line[column] for line in found]
            if column % 2:   # an operator: centred
                centres = [(span["bbox"][0] + span["bbox"][2]) / 2 for span in spans]
                assert centres == pytest.approx([centres[0]] * len(spans), abs=.01), (family, column)
            else:            # a number: right-aligned
                rights = [span["bbox"][2] for span in spans]
                assert rights == pytest.approx([rights[0]] * len(spans), abs=.01), (family, column)
                if family in ("Kv", "ks", "Ks", "Kr"):  # numbers without a script after them
                    boundary = round((rights[0] + 2.4 - column_x(0)) / PITCH_X)
                    assert rights[0] + 2.4 == pytest.approx(column_x(boundary), abs=.3), (family, column)


@pytest.mark.parametrize("name", list(CASES))
def test_every_definition_puts_its_colon_in_one_column(tmp_path: Path, name: str):
    """Reference p1/p2: the "：" of every "ここに、" list in one column, centred on the boundary before body column 9;
    "ここに、" opens each list once."""

    result, pier, embedment = case(name)
    units = content(result, pier, embedment)
    path = render_foundation(result, pier, embedment, tmp_path / "definitions.pdf")
    colons, labels = [], 0
    with pymupdf.open(path) as pdf:
        for page in pdf:
            labels += page.get_text().count("ここに、")
            for block in page.get_text("rawdict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        chars = span["chars"]
                        colons.extend((char["bbox"][0] + char["bbox"][2]) / 2
                                      for previous, char in zip(chars, chars[1:])
                                      if char["c"] == "：" and previous["c"].isspace())
    assert len(colons) == sum(unit.kind == "definition" for unit in units)
    assert colons == pytest.approx([column_x(9)] * len(colons), abs=.06)
    assert labels == sum(unit.lead == "ここに、" for unit in units)
