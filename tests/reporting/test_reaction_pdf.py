"""0600 PDF: the drawn text is the manuscript, pages break by content, bytes are deterministic,
and the appearance meets the independently measured reference roles (reporting-style.md)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from gridlayoutpdf import BreakHint, Equation, Literal, Row, Script, TermStop, Text

from reaction_report_cases import CASES, case

ROOT = Path(__file__).parents[2]
APPEARANCE = ROOT / "tests" / "fixtures" / "reporting" / "appearance" / "reference-style.json"
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
    from webpier.reporting.stages.reaction.manuscript import CellSpec, FigureSpec, TableSpec

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
    if isinstance(value, CellSpec):
        return drawn(value.content)
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


def _placements(pages) -> list[tuple[int, str]]:
    """Each placed block, and each equation of a group of consecutive equations, by its page."""
    found = []
    for number, page in enumerate(pages, 1):
        for placement in page.metadata["placements"]:
            ids = [placement["block_id"]] + [part["metadata"]["equation_block_id"] for part in placement["parts"]
                                             if "equation_block_id" in part["metadata"]]
            found.extend((number, block) for block in ids if block.startswith("0600/"))
    return found


@pytest.mark.parametrize("name", ["current", "pedestal", "ea17"])
def test_pages_break_between_groups_and_never_after_a_heading(name: str):
    from webpier.reporting.stages.reaction import build_reaction, content

    result, pier = case(name)
    units = content(result, pier)
    pages = build_reaction(result, pier).layout()
    where = {block: page for page, block in _placements(pages)}
    groups: dict[str, set[int]] = {}
    for unit in units:
        if unit.group:
            groups.setdefault(unit.group, set()).add(where[unit.identifier])
    assert {group: found for group, found in groups.items() if len(found) > 1} == {}
    kinds = {unit.identifier: unit.kind for unit in units}
    for number, page in enumerate(pages, 1):
        blocks = [placement["block_id"] for placement in page.metadata["placements"]
                  if placement["block_id"].startswith("0600/")]
        assert kinds[blocks[-1]] != "heading", number
    # A heading and the first unit after it are on the same page.
    for index, unit in enumerate(units[:-1]):
        if unit.kind == "heading":
            assert where[unit.identifier] == where[units[index + 1].identifier], unit.key
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


ROLES = {
    "common.chapter": "§6.",
    "common.section": "6.1",
    "common.subsection": "(1)",
    "common.subsubsection": "1)",
    "common.body": "起点側桁は",
    "common.detail_heading": "(a)",
}


def test_typography_matches_the_independent_reference_roles(tmp_path: Path):
    from reportlab.pdfbase.ttfonts import TTFont

    from webpier.reporting.stages.reaction import build_reaction

    reference = json.loads(APPEARANCE.read_text(encoding="utf-8"))["roles"]
    document = build_reaction(*case("current"))
    path = document.render(tmp_path / "appearance.pdf", invariant=True)
    faces = {TTFont(f"verify-{name}", str(face.path), subfontIndex=face.face_index).face.name.decode("ascii"): face
             for name in ("body", "heading", "caption", "dimension") for face in (document.fonts.resolve(name),)}
    with pymupdf.open(path) as pdf:
        samples = [sample for page in pdf for sample in measure.text_samples(page)]
        for role, selector in ROLES.items():
            sample = next(sample for sample in samples if sample.text.startswith(selector))
            face = faces[reference[role]["font"]]
            assert face.pdf_name.startswith(sample.font), role
            assert measure.role_errors(sample.__class__(**{**sample.__dict__, "font": reference[role]["font"]}),
                                       reference[role], anchor_x=58.92) == [], role
        # The bearing derivations use the measured equals columns of 0600 p26.
        for role in ("horizontal.first_equals", "horizontal.result_equals"):
            contract = reference[role]
            matches = [sample for sample in samples if sample.text.startswith("=")
                       and abs(sample.x - contract["source"]["selector_x_pt"]) < .5]
            assert matches, role
            assert measure.role_errors(sample.__class__(**{**matches[0].__dict__, "font": contract["font"]}),
                                       {**contract, "font": contract["font"]}, anchor_x=58.92) == [], role
        lhs = next(sample for sample in samples if sample.text.startswith("T / n"))
        assert measure.role_errors(lhs.__class__(**{**lhs.__dict__, "font": "MS-Mincho"}),
                                   reference["horizontal.formula_lhs"], anchor_x=58.92) == []
        # Figure caption and dimensions: MS PGothic 9.9 pt and Calibri 8 pt.
        caption = next(sample for sample in samples if sample.text.replace(" ", "") == "側面図")
        assert faces[reference["figure.caption"]["font"]].pdf_name.startswith(caption.font)
        assert caption.size == pytest.approx(reference["figure.caption"]["size_pt"], abs=.1)
        dimension = next(sample for sample in samples if sample.text == "9.000" and sample.size < 9)
        assert faces[reference["figure.dimension"]["font"]].pdf_name.startswith(dimension.font)
        assert dimension.size == pytest.approx(reference["figure.dimension"]["size_pt"], abs=.1)
        assert all(measure.monochrome_errors(page) == [] for page in pdf)


def _table_bands(page: pymupdf.Page, x: float, y: float) -> list[float]:
    """Horizontal rule bands of the table that contains (x, y): the run of bands less than 30 pt apart."""
    bands = [band.coordinate for band in measure.painted_rule_bands(measure.native_rules(page), axis="h", crossing=x)]
    below = next(index for index, coordinate in enumerate(bands) if coordinate > y)
    first = below - 1
    while first > 0 and bands[first] - bands[first - 1] < 30:
        first -= 1
    last = below
    while last + 1 < len(bands) and bands[last + 1] - bands[last] < 30:
        last += 1
    return bands[first:last + 1]


@pytest.mark.parametrize("contract_name,first_cell,rows", [
    ("reaction.girder", "固定死荷重", 6),     # the support table: header + 5 loads
    ("reaction.impact", "列車反力", 9),        # the impact table: header + R + 3 single + 4 double
])
def test_reaction_tables_have_the_measured_row_height(tmp_path: Path, contract_name: str, first_cell: str, rows: int):
    from webpier.reporting.stages.reaction import render_reaction

    contract = json.loads(APPEARANCE.read_text(encoding="utf-8"))["tables"][contract_name]
    path = render_reaction(*case("current"), tmp_path / "rows.pdf")
    with pymupdf.open(path) as pdf:
        page = next(page for page in pdf if page.search_for(first_cell))
        anchor = page.search_for(first_cell)[0]
        bands = _table_bands(page, anchor.x1 + 150, anchor.y1)
        assert measure.table_errors(bands, [contract["nominal_row_height_pt"]] * rows) == []
        widths = {round(band.width, 2) for band in measure.painted_rule_bands(
            measure.native_rules(page), axis="h", crossing=anchor.x1 + 150)}
        assert widths <= {contract["thin_rule_pt"], 2 * contract["thin_rule_pt"], contract["thick_rule_pt"]}


def test_the_horizontal_summary_has_the_measured_row_and_header_heights(tmp_path: Path):
    from webpier.reporting.stages.reaction import render_reaction

    contract = json.loads(APPEARANCE.read_text(encoding="utf-8"))["tables"]["reaction.horizontal_summary"]
    path = render_reaction(*case("current"), tmp_path / "summary.pdf")
    with pymupdf.open(path) as pdf:
        page = next(page for page in pdf if page.search_for("起点桁"))
        anchor = page.search_for("荷重種別")[0]
        bands = _table_bands(page, anchor.x1 + 200, anchor.y1)
        heights = [28.56] + [contract["nominal_row_height_pt"]] * 10
        assert measure.table_errors(bands, heights) == []
