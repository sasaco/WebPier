"""0600 PDF: the drawn text is the manuscript, pages break by content, bytes are deterministic, and the pages stand
on GridLayoutPdf's common grid (A4, 16.08 x 15.48 pt cells): every position a body column, every height whole grid
rows, the report's faces at their sizes, tables framed medium and ruled hair (plan glp-0.2.0-grid)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from gridlayoutpdf import (A4_PORTRAIT_REFERENCE, BreakHint, Equation, FontRegistry, Literal, Row, Script,
                           TermStop, Text)

from reaction_report_cases import CASES, case
from webpier.reporting.equations import terms

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure_0600",
                                               ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

PAGE_NUMBER = re.compile(r"^\d+ - \d+$", re.MULTILINE)  # the reference prints no page numbers


def drawn(value: Any) -> str:
    """What a node draws as text: term columns and break hints draw nothing."""
    from webpier.reporting.equations import Definition
    from webpier.reporting.stages.reaction.manuscript import CellSpec, FigureSpec, Pair, TableSpec, Wrapped

    if isinstance(value, str):
        return value
    if isinstance(value, (TermStop, BreakHint)):
        return ""
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(drawn(item) for item in value.items)
    if isinstance(value, Script):
        return drawn(value.base) + drawn(value.subscript or "") + drawn(value.superscript or "")
    if isinstance(value, tuple) and all(isinstance(item, Definition) for item in value):
        return "ここに、" + "".join(drawn(item.symbol) + "：" + drawn(item.text) for item in value)
    if isinstance(value, Equation):
        result = "" if value.result is None else value.result_relation + drawn(value.result)
        return value.label + drawn(value.lhs) + value.relation + drawn(value.rhs) + result + drawn(value.unit or "")
    if isinstance(value, Pair):
        return value.first + value.second
    if isinstance(value, CellSpec):
        return drawn(value.content)
    if isinstance(value, Wrapped):
        return drawn(value.node)
    if isinstance(value, TableSpec):
        return "".join(drawn(cell) for row in value.rows for cell in row)
    if isinstance(value, FigureSpec):
        return "".join(value.labels)
    raise TypeError(type(value).__name__)


def squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def scene_text(pages) -> str:
    return squeeze("".join(command.text for page in pages for command in page.commands
                           if isinstance(command, Text)))


@pytest.mark.parametrize("name", list(CASES))
def test_the_scene_draws_every_record_and_the_pdf_has_the_same_text(tmp_path: Path, name: str):
    from webpier.reporting.stages.reaction import build_reaction, content, render_reaction

    result, pier = case(name)
    pages = build_reaction(result, pier).layout()
    expected = squeeze("".join(drawn(unit.value) for unit in content(result, pier)))
    assert Counter(scene_text(pages)) == Counter(expected)
    path = render_reaction(result, pier, tmp_path / "0600.pdf")
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(pages)
        for page, scene in zip(pdf, pages):
            pdf_chars = Counter(squeeze(page.get_text()))
            scene_chars = Counter(squeeze("".join(command.text for command in scene.commands
                                                  if isinstance(command, Text))))
            assert pdf_chars == scene_chars
            assert not PAGE_NUMBER.search(page.get_text())
            assert not page.get_images()


def test_text_is_drawn_in_manuscript_order():
    from webpier.reporting.stages.reaction import build_reaction, content

    result, pier = case("current")
    pages = build_reaction(result, pier).layout()
    drawn_text = scene_text(pages)
    position = 0
    for unit in content(result, pier):
        if unit.kind in ("heading", "paragraph", "equation"):
            text = squeeze(drawn(unit.value))
            found = drawn_text.find(text, position)
            assert found >= 0, unit.key
            position = found + len(text)


def _page_texts(pages) -> list[str]:
    return [squeeze("".join(command.text for command in page.commands if isinstance(command, Text)))
            for page in pages]


def _text_pages(units, pages) -> dict[str, int]:
    """The page of each unit that draws text in its own run (a heading, a sentence, a formula, a pair), found in
    manuscript order in the drawn text: the equations of one group share one block, whatever the lines they take."""
    texts = _page_texts(pages)
    found: dict[str, int] = {}
    page, position = 0, 0
    for unit in units:
        if unit.kind not in ("heading", "paragraph", "equation", "pair", "math"):
            continue
        text = squeeze(drawn(unit.value))
        while texts[page].find(text, position) < 0:
            page, position = page + 1, 0
            assert page < len(texts), unit.key
        position = texts[page].find(text, position) + len(text)
        found[unit.identifier] = page + 1
    return found


@pytest.mark.parametrize("name", ["current", "pedestal", "ea17"])
def test_pages_break_between_groups_and_never_after_a_heading(name: str):
    from webpier.reporting.stages.reaction import build_reaction, content

    result, pier = case(name)
    units = content(result, pier)
    pages = build_reaction(result, pier).layout()
    where = _text_pages(units, pages)
    groups: dict[str, set[int]] = {}
    for unit in units:
        if unit.group:
            groups.setdefault(unit.group, set()).add(where[unit.identifier])
    assert {group: found for group, found in groups.items() if len(found) > 1} == {}
    kinds = {unit.identifier: unit.kind for unit in units}
    for number, page in enumerate(pages, 1):
        blocks = [placement["block_id"] for placement in page.metadata["placements"]
                  if placement["block_id"] in kinds]
        assert kinds[blocks[-1]] != "heading", number
    # A heading and the first unit after it are on the same page (a table or a figure: its placement).
    placed = {placement["block_id"]: number for number, page in enumerate(pages, 1)
              for placement in page.metadata["placements"]}
    for index, unit in enumerate(units[:-1]):
        if unit.kind == "heading":
            following = units[index + 1]
            assert where[unit.identifier] == where.get(following.identifier, placed.get(following.identifier)), \
                unit.key
    # Content decides the page count: no blank page, i.e. no page without body text.
    assert all(any(isinstance(command, Text) and command.text.strip()
                   for command in page.commands) for page in pages)


def test_same_input_gives_the_same_bytes_in_this_and_another_process(tmp_path: Path):
    from webpier.reporting.stages.reaction import render_reaction

    first = render_reaction(*case("current"), tmp_path / "a.pdf").read_bytes()
    second = render_reaction(*case("current"), tmp_path / "b.pdf").read_bytes()
    assert first == second
    assert b"CreationDate" not in first or b"D:20000101000000" in first
    script = ("import sys; sys.path[:0] = [sys.argv[2], sys.argv[3]]\n"
              "from reaction_report_cases import case\n"
              "from webpier.reporting.stages.reaction import render_reaction\n"
              "render_reaction(*case('current'), sys.argv[1])\n")
    other = tmp_path / "c.pdf"
    subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(other), str(Path(__file__).parent), str(ROOT)],
                   check=True, cwd=tmp_path)
    assert other.read_bytes() == first
    assert render_reaction(*case("pedestal"), tmp_path / "d.pdf").read_bytes() != first


def test_render_replaces_the_target_only_after_a_complete_layout(tmp_path: Path):
    from dataclasses import replace

    from gridlayoutpdf import LayoutError

    from webpier.core.printed import Printed
    from webpier.reporting.stages.reaction import render_reaction

    result, pier = case("current")
    huge = replace(result.self_weight.beam, weight=Printed(1e40, 2, "kN"))
    broken = replace(result, self_weight=replace(result.self_weight, beam=huge))
    path = tmp_path / "previous.pdf"
    path.write_bytes(b"previous-published-bytes")
    with pytest.raises(LayoutError):
        render_reaction(broken, pier, path)
    assert path.read_bytes() == b"previous-published-bytes"


# --- the common grid (GridLayoutPdf 0.2.0: A4, 16.08 x 15.48 pt cells, 30 columns x 47 rows) --------------------------

GRID = A4_PORTRAIT_REFERENCE.grid
BASELINE = 11.0  # a body line's baseline below the top of its grid row (MS Mincho / MS Gothic 10 pt)


def column_x(column: int) -> float:
    return GRID.origin_x + column * GRID.pitch_x


def row_top(baseline: float) -> float:
    """The top of the grid row whose body line has this baseline."""
    return baseline - BASELINE


@dataclass(frozen=True)
class Span:
    text: str
    face: str
    size: float
    x0: float
    x1: float
    baseline: float
    page: int


def spans(pdf) -> list[Span]:
    """Every upright text span, its face named by the hash in GridLayoutPdf's PDF font name (MS Gothic: the file that
    also holds MS PGothic)."""
    registry = FontRegistry()
    faces = {"GLP_" + registry.resolve(name).sha256: name for name in ("MS Gothic", "MS Mincho", "Calibri")}
    found = []
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                if abs(line["dir"][0] - 1) > 1e-6:
                    continue
                for span in line["spans"]:
                    if span["text"].strip():
                        face = next((name for prefix, name in faces.items() if prefix.startswith(span["font"])),
                                    span["font"])
                        found.append(Span(span["text"].strip(), face, round(span["size"], 2), span["bbox"][0],
                                          span["bbox"][2], span["origin"][1], page.number + 1))
    return found


ROLES = (  # (the text a span starts with, its body column, its face)
    ("§6.", 0, "MS Gothic"),  # chapter
    ("6.1", 1, "MS Gothic"),  # section
    ("(1)", 2, "MS Gothic"),  # subsection
    ("1)", 3, "MS Gothic"),  # item
    ("(a)", 4, "MS Gothic"),  # detail
    ("制動荷重および始動荷重の特性値は", 4, "MS Mincho"),  # body
    ("・1.0 LR", 4, "MS Mincho"),  # a combination of 6.4.1 (2)
    ("※ T1", 5, "MS Mincho"),  # a bearing derivation
)


@pytest.fixture(scope="module")
def current_pdf(tmp_path_factory):
    from webpier.reporting.stages.reaction import render_reaction

    path = render_reaction(*case("current"), tmp_path_factory.mktemp("grid") / "0600.pdf")
    with pymupdf.open(path) as pdf:
        yield pdf


def test_the_text_stands_in_grid_columns_and_rows_in_the_named_faces(current_pdf):
    found = spans(current_pdf)
    for start, column, face in ROLES:
        sample = next(span for span in found if span.text.startswith(start))
        assert (sample.face, sample.size) == (face, 10.0), start
        # A glyph's ink may start a little inside its column ("(" and "1" have side bearings).
        assert column_x(column) - .01 <= sample.x0 < column_x(column) + 2.5, start
        assert (sample.baseline - GRID.origin_y) % GRID.pitch_y == pytest.approx(BASELINE, abs=.01), start
    # Every face is one of the report's: 10 pt text, 6.5 pt scripts, the figure titles in MS PGothic 10 pt and the
    # dimensions in Calibri 8 pt.
    assert {(span.face, span.size) for span in found} <= {("MS Mincho", 10.0), ("MS Mincho", 6.5),
                                                          ("MS Gothic", 10.0), ("Calibri", 8.0)}
    caption = next(span for span in found if span.text.replace(" ", "") == "側面図")
    dimension = next(span for span in found if span.text == "9.000" and span.size < 9)
    assert (caption.face, caption.size) == ("MS Gothic", 10.0)
    assert (dimension.face, dimension.size) == ("Calibri", 8.0)
    assert all(measure.monochrome_errors(page) == [] for page in current_pdf)


def test_nothing_is_drawn_outside_the_body_columns(current_pdf):
    left, right = column_x(0) - .5, column_x(GRID.columns) + .5
    for page in current_pdf:
        assert [span.text for span in spans([page]) if span.x0 < left or span.x1 > right] == [], page.number + 1
        assert [drawing["rect"] for drawing in page.get_drawings()
                if drawing["rect"].x0 < left or drawing["rect"].x1 > right] == [], page.number + 1


def _relations(pdf) -> Counter:
    """The 10 pt "=" whose centre stands on a body column boundary, by that boundary."""
    found: Counter = Counter()
    for page in pdf:
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    for char in span["chars"]:
                        if char["c"] == "=" and abs(span["size"] - 10) < .01:
                            boundary = ((char["bbox"][0] + char["bbox"][2]) / 2 - GRID.origin_x) / GRID.pitch_x
                            if abs(boundary - round(boundary)) < .01:
                                found[round(boundary)] += 1
    return found


def test_the_relations_stand_on_the_formula_columns(current_pdf):
    from webpier.reporting.stages.reaction.manuscript import (
        BODY, CONCLUSION_EQUAL, MARK_EQUAL, RESULT_EQUAL, SHORT_EQUAL, UNIT_START, VERTICAL_EQUAL, WIDE_EQUAL,
    )

    relations = _relations(current_pdf)
    # Every "=" on a column boundary is on a formula column (荷重修正係数 ρf takes six columns before its "=").
    assert set(relations) <= {SHORT_EQUAL, MARK_EQUAL, CONCLUSION_EQUAL, VERTICAL_EQUAL, WIDE_EQUAL, RESULT_EQUAL,
                              BODY + 6}
    assert relations[RESULT_EQUAL] > 150 and relations[SHORT_EQUAL] > 150 and relations[WIDE_EQUAL] > 40
    # The unit of a result starts at its column.
    units = [span for span in spans(current_pdf) if span.text in ("kN", "m", "kN・m")
             and abs(span.x0 - column_x(UNIT_START)) < 1]
    assert len(units) > 150


def _rows(page: pymupdf.Page, x: float, top: float) -> list[float]:
    """The horizontal rules of the table under *top* crossing the paper x *x*: their centres, top down."""
    found = set()
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                (x0, y0), (x1, y1) = (item[1].x, item[1].y), (item[2].x, item[2].y)
                if abs(y0 - y1) < .01 and min(x0, x1) <= x <= max(x0, x1) and y0 > top:
                    found.add(round(y0, 2))
    bands: list[float] = []
    for y in sorted(found):
        if bands and y - bands[-1] > 2 * GRID.pitch_y + 1:
            break  # the next table
        if not bands or y - bands[-1] > .6:
            bands.append(y)
    return bands


@pytest.mark.parametrize("first_cell,rows", [
    ("固定死荷重", 6),  # the support table: header + 5 loads
    ("列車反力", 9),  # the impact table: header + R + 3 single + 4 double
    ("荷重種別", 11),  # the horizontal summary along the track: header + 8 combinations + 2 seismic
])
def test_a_table_row_is_a_grid_row_framed_medium_and_ruled_hair(current_pdf, first_cell: str, rows: int):
    page = next(page for page in current_pdf if page.search_for(first_cell))
    anchor = page.search_for(first_cell)[0]
    crossing = column_x(26) - 2  # a column of numbers of each table, where every row has its rules
    bands = _rows(page, crossing, anchor.y0 - 2 * GRID.pitch_y)
    # The frame's medium rule lies inside the table's boundary (half its 1.0 pt), the hair rules on the boundaries.
    tops = [bands[0] - .5, *bands[1:rows], bands[rows] + .5]
    assert [round((low - high) / GRID.pitch_y, 3) for high, low in zip(tops, tops[1:])] == [1] * rows
    offset = (tops[0] - GRID.origin_y) / GRID.pitch_y
    assert offset == pytest.approx(round(offset), abs=1e-3)
    widths = {round(drawing.get("width") or 0, 2) for drawing in page.get_drawings() if drawing["type"] == "s"
              and drawing["rect"].height < .01 and tops[0] - 1 <= drawing["rect"].y0 <= tops[-1] + 1
              and drawing["rect"].x0 <= crossing <= drawing["rect"].x1}
    assert widths == {.25, 1.0}


def _baselines(page: Any, test) -> list[float]:
    return sorted(span["origin"][1] for block in page.get_text("dict")["blocks"] for line in block.get("lines", ())
                  for span in line["spans"] if test(span["text"]))


@pytest.mark.parametrize("name", ["current", "ea17"])
def test_each_bearing_derivation_is_bracketed_by_the_rule(tmp_path: Path, name: str):
    """0600 p16: a medium rule on the left edge of the column of "※", from the row under "※ T1" to the row above
    "※ ∴ H" (whole grid rows: the grid Excel writes it as the cells' left border); one per girder and combination."""
    from webpier.reporting.stages.reaction import render_reaction
    from webpier.reporting.stages.reaction.manuscript import RULE_X

    rules = 0
    with pymupdf.open(render_reaction(*case(name), tmp_path / "rule.pdf")) as pdf:
        for page in pdf:
            bars = sorted((drawing["rect"] for drawing in page.get_drawings()
                           if drawing["type"] == "f" and abs(drawing["rect"].width - 1.0) < .01),
                          key=lambda rect: rect.y0)
            runs: list[list[float]] = []
            for bar in bars:
                assert (bar.x0 + bar.x1) / 2 == pytest.approx(column_x(RULE_X), abs=.01)
                if runs and abs(runs[-1][1] - bar.y0) < .01:
                    runs[-1][1] = bar.y1
                else:
                    runs.append([bar.y0, bar.y1])
            marks = _baselines(page, lambda text: text.startswith("※"))
            for top, bottom in runs:
                above = max(mark for mark in marks if mark < top)
                below = min(mark for mark in marks if mark > bottom)
                assert top == pytest.approx(row_top(above) + GRID.pitch_y, abs=.01)
                assert bottom == pytest.approx(row_top(below), abs=.01)
                rules += 1
    assert rules == 2 * 8 + 2 * 2  # both girders of the eight combinations and of the two seismic actions


def test_the_fixed_bearing_candidate_puts_its_result_in_the_result_column(current_pdf):
    """07 7-5: "T − 1/2μ・Rm = 160.00 − 1/2 × 0.10 × 2370.00 = 41.50 kN": its terms take more columns than its
    line holds, and its result stands on the next row, in the result column."""
    from webpier.reporting.stages.reaction.manuscript import UNIT_START

    found = 0
    for page in current_pdf:
        units = [span.baseline for span in spans([page]) if span.text == "kN"
                 and abs(span.x0 - column_x(UNIT_START)) < 1]
        for baseline in _baselines(page, lambda text: text.startswith("T - 1/2") or text.startswith("T − 1/2")):
            assert any(abs(unit - baseline - GRID.pitch_y) < .01 for unit in units), baseline
            found += 1
    assert found == 8


def test_a_long_formula_continues_with_its_operator_in_the_relation_column(current_pdf):
    """Rm = 1.1 × 5740.00 + … wraps before "+": the next line takes "+" in the "=" column and its terms from the
    column after it; the result stands on the last line."""
    from webpier.reporting.stages.reaction.manuscript import VERTICAL_EQUAL

    continued = 0
    for page in current_pdf:
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    chars = [char for char in span["chars"] if not char["c"].isspace()]
                    if chars and chars[0]["c"] == "+" and abs(span["size"] - 10) < .01:
                        centre = (chars[0]["bbox"][0] + chars[0]["bbox"][2]) / 2
                        if abs(centre - column_x(VERTICAL_EQUAL)) < .01:
                            continued += 1
    assert continued >= 2 * 8  # each Rm with the train, at least one further line


def test_the_table_rows_take_a_grid_row_per_line_of_their_tallest_cell():
    from webpier.reporting.stages.reaction.layout import _heights
    from webpier.reporting.stages.reaction.manuscript import CellSpec, TableSpec

    spec = TableSpec((2, 2, 2), ((CellSpec("a\nb\nc\nd", rowspan=2), CellSpec("x"), CellSpec("y\nz")),
                                 (CellSpec("1"), CellSpec("2"))), header_rows=0)
    # The first row holds two lines; the spanning cell's fourth line goes to the last row it spans.
    assert _heights(spec) == [2, 2]


def test_a_formula_whose_terms_cannot_break_is_reported():
    from gridlayoutpdf import LayoutOverflowError

    from webpier.reporting.stages.reaction.layout import document
    from webpier.reporting.stages.reaction.manuscript import Manuscript

    m = Manuscript()
    m.equation("long", "x", terms(*["123456.789"] * 12), checked=False)  # no operator to break before
    with pytest.raises(LayoutOverflowError):
        document(m.units).layout()
