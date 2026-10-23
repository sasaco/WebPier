"""Blank lines in every report follow the reference (.claude/docs/Example橋脚/output) on the common grid:

body rows advance one grid row (15.48 pt) and the first row's baseline is that of the grid's first row on every
page (no blank line is left at a page top); a heading has exactly one blank line before and after it (two grid
rows between the baselines), also between two headings (blank lines never stack, so never three grid rows).

A body baseline is the baseline of 10 pt text that lies on the grid rows from the first one; the
off-row baselines of fraction numerators, table cells and figure labels are not body baselines.
Table rows are not on the body rows in the reference either (an open table's rows can fall on them by
chance), so a table's extent is taken from the same Document's layout: a placement whose parts carry
the table "cells" metadata covers rows [row, row + rows) of its page. Baselines inside it are not body
baselines. After a multi-line equation group the rows may continue from another origin, so a heading's
neighbours are taken on the rows through the heading itself.

The PDFs are WebPier's own pages (build_*(...).render()); the FEMPython load diagram pages of 0610 / 0620
(decision 44) are not part of them and are not measured.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from foundation_report_cases import case as foundation_case
from foundation_check_cases import chapter as foundation_chapter, result as foundation_result
from frame_report_cases import chain, transverse_chain
from reaction_report_cases import case as reaction_case
from webpier.reporting.document import paragraph, report
from webpier.reporting.fonts import load_fonts
from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check
from webpier.calc.detailing import calculate_detailing
from webpier.inputs import parse_input
from webpier.reporting.stages.column_check import LONGITUDINAL as CHAPTER_8, TRANSVERSE as CHAPTER_9
from webpier.reporting.stages.column_check import build_column_check
from webpier.reporting.stages.detailing import build_detailing
from webpier.reporting.stages.foundation import build_foundation
from webpier.reporting.stages.foundation_check import build_foundation_check
from webpier.reporting.stages.longitudinal import build_longitudinal
from webpier.reporting.stages.reaction import build_reaction
from webpier.reporting.stages.seismic_longitudinal import build_seismic_longitudinal
from webpier.reporting.stages.seismic_transverse import build_seismic_transverse
from webpier.reporting.stages.transverse import build_transverse
from webpier.reporting.styles import HEADING_FONT

CURRENT = Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json"
FIRST = next(command.y for command in report(paragraph("本文", left=0)).layout()[0].commands
             if getattr(command, "text", "") == "本文")
ROW = 15.48
SIZE = 10
BLANK = 2 * ROW  # a line, one blank line, a line
TWO_BLANKS = 3 * ROW
# §5. / 5.1 / 6.4.1 / (1) / 1) / (a) followed by the heading text.
NUMBERED = re.compile(r"^\s*(§\d+\.|\d+(\.\d+)+ |\(\d+\) |\d+\) |\([a-z]\) )")
FLOAT_HEIGHT = 12.0  # table rules and figures are taller; a fraction bar is a flat line

BUILDERS: dict[str, Callable[[str], Any]] = {
    # decision 73: the input alone
    "0400": lambda name: build_detailing(calculate_detailing(parse_input(json.loads(
        CURRENT.read_text(encoding="utf-8"))))),
    "0500": lambda name: build_foundation(*foundation_case(name)),
    "0600": lambda name: build_reaction(*reaction_case(name)),
    "0610": lambda name: build_longitudinal(chain(name)[2], chain(name)[1], chain(name)[0]),
    "0620": lambda name: build_transverse(transverse_chain(name)[2], transverse_chain(name)[1],
                                          transverse_chain(name)[0]),
    "0710": lambda name: build_seismic_longitudinal(chain(name)[3], chain(name)[1], chain(name)[0]),
    "0720": lambda name: build_seismic_transverse(transverse_chain(name)[3], transverse_chain(name)[1], transverse_chain(name)[0]),
    # one Document before each of Capacita's sections (decision 48); across the track with the two checks Capacita
    # skips for Example2, each ending with the reason
    "0611": lambda name: build_column_check(calculate_column_check(chain(name)[0], chain(name)[2], LONGITUDINAL),
                                            CHAPTER_8),
    "0621": lambda name: build_column_check(
        calculate_column_check(transverse_chain(name)[0], transverse_chain(name)[2], TRANSVERSE), CHAPTER_9,
        ("shear_durability", "bending_serviceability")),
    # decision 54: with the reactions of the hand calculation (the input is current.json made sandy)
    "0612": lambda name: build_foundation_check(foundation_result("0612"), foundation_chapter("0612")),
    "0622": lambda name: build_foundation_check(foundation_result("0622"), foundation_chapter("0622")),
}
# The fixture input of every stage (tests/fixtures/inputs/current.json).
PARAMETERS = [(stage, "current") for stage in BUILDERS]


def _on_row(y: float, origin: float = FIRST) -> bool:
    rows = (y - origin) / ROW
    return abs(rows - round(rows)) * ROW < 0.02


HEADING_PDF_NAME = load_fonts().resolve(HEADING_FONT).pdf_name


def _heading_font(font: str) -> bool:
    return len(font) >= 20 and HEADING_PDF_NAME.startswith(font)


def _tables(page: Any) -> list[tuple[float, float]]:
    """The y extents of the tables laid out on a ScenePage: placements whose parts carry "cells"."""
    grid = page.profile.grid
    return [(grid.y(placement["row"]), grid.y(placement["row"] + placement["rows"]))
            for placement in page.metadata["placements"]
            if any("cells" in part["metadata"] for part in (*placement["prefix"], *placement["parts"]))]


def _pages(path: Path, laid_out: Any) -> list[dict]:
    """Per page: 10 pt baselines (all), body baselines, numbered heading baselines, float and table extents.

    *laid_out* are the same Document's ScenePages, one per PDF page."""
    found = []
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(laid_out)
        for page, scene in zip(pdf, laid_out):
            spans: dict[float, list[dict]] = {}
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if abs(span["size"] - SIZE) < .05 and span["text"].strip():
                            spans.setdefault(round(span["origin"][1], 2), []).append(span)
            tables = _tables(scene)
            body = sorted(y for y in spans if _on_row(y) and not any(top < y <= bottom for top, bottom in tables))
            headings = [y for y in spans if any(_heading_font(span["font"]) and NUMBERED.match(span["text"])
                                               for span in spans[y])]
            floats = [(item["rect"].y0, item["rect"].y1) for item in page.get_drawings()
                      if item["rect"].height > FLOAT_HEIGHT]
            rules = [item["rect"].y0 for item in page.get_drawings()]
            found.append({"all": sorted(spans), "body": body, "headings": headings,
                          "floats": floats, "rules": rules, "tables": tables})
    return found


@pytest.fixture(scope="module", params=PARAMETERS, ids=[f"{stage}-{name}" for stage, name in PARAMETERS])
def pages(request, tmp_path_factory) -> tuple[str, list[dict]]:
    stage, name = request.param
    built = BUILDERS[stage](name)
    directory = tmp_path_factory.mktemp(f"spacing-{stage}-{name}")
    found = []
    for index, document in enumerate(built if isinstance(built, tuple) else (built,)):
        path = document.render(directory / f"{stage}-{index}.pdf", invariant=True)
        found += _pages(path, document.layout())
    return stage, found


def test_every_page_starts_on_its_first_row(pages):
    """No blank line is left at a page top. A page that begins with a table or figure (a drawing above its
    first 10 pt baseline, or a laid-out table around it: an open table has no rule above) is excluded: its first
    text is a cell or a label, not a body row."""
    _, found = pages
    checked = 0
    for number, page in enumerate(found, 1):
        first = page["all"][0]
        if any(top < first for top in page["rules"]) or any(top < first <= bottom for top, bottom in page["tables"]):
            continue
        checked += 1
        assert first == pytest.approx(FIRST, abs=.01), f"page {number}"
    assert checked >= 1


def test_a_heading_has_one_blank_line_before_and_after_it(pages):
    """The body baselines next to a heading are two grid rows away. Excluded: a heading first or last on its page
    (no neighbour there), and a neighbour across a table, figure or load diagram (a drawing or a laid-out table
    between them)."""
    stage, found = pages
    checked = 0
    for number, page in enumerate(found, 1):
        for heading in page["headings"]:
            rows = [y for y in page["all"] if _on_row(y, heading)]
            index = rows.index(heading)
            neighbours = ([rows[index - 1]] if index else []) + ([rows[index + 1]] if index + 1 < len(rows) else [])
            for neighbour in neighbours:
                low, high = sorted((heading, neighbour))
                if any(top < high and bottom > low for top, bottom in (*page["floats"], *page["tables"])):
                    continue
                checked += 1
                assert high - low == pytest.approx(BLANK, abs=.02), f"{stage} page {number}: {low} → {high}"
    assert checked >= 8


def test_blank_lines_never_stack(pages):
    """Two body baselines are never three grid rows apart (a blank line after one heading and before the next).

    Excluded: baselines inside a table (its laid-out extent, see the module docstring), and two body
    baselines with a table between them (the table's rows, not blank lines, separate them)."""
    stage, found = pages
    checked = 0
    for number, page in enumerate(found, 1):
        for low, high in zip(page["body"], page["body"][1:]):
            if any(low < bottom and top < high for top, bottom in page["tables"]):
                continue
            checked += 1
            assert high - low != pytest.approx(TWO_BLANKS, abs=.02), f"{stage} page {number}: {low} → {high}"
    assert checked >= 20


def test_blank_adds_one_blank_line_only_after_content():
    from gridlayoutpdf import KeepWithNext, Spacer

    from webpier.reporting.document import blank, is_blank, paragraph, spacer

    out: list = []
    blank(out)
    assert out == []  # nothing at the start of a report
    text = paragraph("本文")
    out.append(text)
    blank(out)
    blank(out)
    assert out == [text, spacer()] and out[1].discard_at_page_top
    out[1] = KeepWithNext(out[1])
    blank(out)
    assert len(out) == 2 and is_blank(out[1]) and not is_blank(text)
    assert isinstance(spacer(), Spacer)
