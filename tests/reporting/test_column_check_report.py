"""The 0611 / 0621 report (decisions 48, 121; ADR-0008): Capacita's pages of each section, joined in report order.

Capacita prints its commentary (the group headings numbered from n.5, the check formulas, the symbols, the flowchart)
within each section's pages (WDJ calc.print_commentary_checked; run-rc --commentary-chapter n
--commentary-first-section 5): WebPier lays out nothing of the report. A check Capacita skipped for zero forces has
no pages and nothing in the report. 0400 refers to the numbers Capacita gave the sections, and the foundation check
follows the last of them.

Capacita's pages are stand-ins here (one page per section, two for the section force list, each saying which section
it is), cut by their ranges as the real report is.
"""

from __future__ import annotations

import io
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen import canvas

from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.inputs import parse_input
from webpier.reporting.assembly import page_range
from webpier.reporting.stages.column_check import (DURABILITY, FOLLOWING_ALL, LONGITUDINAL as CHAPTER_8, REBAR_AMOUNT,
                                                   TRANSVERSE as CHAPTER_9, following_section, reference,
                                                   render_column_check)

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
MARK = "FAKE CAPACITA"
# Capacita skips these across the track for Example2 (column_section_check_09.json, skipped_by_capacita)
SKIPPED = ("shear_durability", "bending_serviceability")


def check(*, transverse=False, **conditions):
    data = deepcopy(CURRENT)
    data["柱の断面照査"] |= conditions
    pier = parse_input(data)
    reaction, foundation = calculate_reaction(pier), calculate_foundation(pier)
    if transverse:
        return pier, calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE)
    return pier, calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL)


def capacita_report(sections, skipped=()) -> tuple[bytes, dict]:
    """A stand-in Capacita report and the page range of each section: section_forces has two pages, every other
    section one; none for a skipped one."""
    stream, ranges, number = io.BytesIO(), {}, 0
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for section in sections:
        if section in skipped:
            continue
        count = 2 if section == "section_forces" else 1
        ranges[section] = (number + 1, number + count)
        for index in range(count):
            number += 1
            page.drawString(60, 780, f"{MARK} {section} {index + 1}")
            page.showPage()
    page.save()
    return stream.getvalue(), ranges


def capacita(sections, skipped=()) -> dict[str, bytes]:
    """The pages the report receives: each section's pages by its id, cut by its range; a skipped one is not in it."""
    pdf, ranges = capacita_report(sections, skipped)
    return {section: page_range(pdf, *found) for section, found in ranges.items()}


def render(tmp_path: Path, *, transverse=False, skipped=(), **conditions) -> list[str]:
    _, result = check(transverse=transverse, **conditions)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = render_column_check(result, tmp_path / "report.pdf", capacita(result.sections, skipped))
    with pymupdf.open(path) as document:
        return [page.get_text().strip() for page in document]


def test_the_report_is_capacitas_pages_in_report_order(tmp_path):
    assert render(tmp_path) == [f"{MARK} {section} {index}" for section, index in (
        ("section_forces", 1), ("section_forces", 2), ("bending_safety_destruction", 1),
        ("shear_safety_destruction", 1), ("bending_durability", 1), ("shear_durability", 1),
        ("bending_serviceability", 1), ("bending_restorability", 1), ("shear_restorability", 1),
        ("bending_rebar_amount", 1))]


def test_a_check_capacita_skipped_has_nothing_in_the_report(tmp_path):
    """Example2 across the track: no pages, and no reason printed in their place (decision 121 amends decision 48)."""
    pages = render(tmp_path, transverse=True, skipped=SKIPPED)
    assert [text.split()[2] for text in pages] == [
        "section_forces", "section_forces", "bending_safety_destruction", "shear_safety_destruction",
        "bending_durability", "bending_restorability", "shear_restorability", "bending_rebar_amount"]
    assert all(text.startswith(MARK) for text in pages)


def test_without_the_appearance_check_there_are_no_pages_of_it(tmp_path):
    pages = render(tmp_path, 外観の照査="行わない")
    assert len(pages) == 9 and not any("bending_serviceability" in text for text in pages)


def test_the_report_is_the_same_bytes_for_the_same_pages(tmp_path):
    _, result = check()
    given = capacita(result.sections)
    one = render_column_check(result, tmp_path / "one.pdf", given).read_bytes()
    two = render_column_check(result, tmp_path / "two.pdf", given).read_bytes()
    assert one == two


def test_the_section_force_list_must_have_its_pages(tmp_path):
    """Capacita never skips the section force list (the first section)."""
    _, result = check()
    first = result.sections[0]
    given = {section: found for section, found in capacita(result.sections).items() if section != first}
    with pytest.raises(ValueError, match=f"差し込むページ {first} がありません"):
        render_column_check(result, tmp_path / "report.pdf", given)
    assert not (tmp_path / "report.pdf").exists()


def test_pages_of_a_section_not_asked_for_are_an_error(tmp_path):
    _, result = check(外観の照査="行わない")
    given = capacita((*result.sections, "bending_serviceability"))
    with pytest.raises(ValueError, match="柱の断面照査にない節のページです: bending_serviceability"):
        render_column_check(result, tmp_path / "report.pdf", given)


def test_a_page_range_is_cut_as_it_is():
    given, _ = capacita_report(["section_forces", "bending_safety_destruction"])
    with pymupdf.open(stream=page_range(given, 2, 3), filetype="pdf") as cut:
        assert [page.get_text().strip() for page in cut] == [f"{MARK} section_forces 2",
                                                            f"{MARK} bending_safety_destruction 1"]
    for first, last in ((0, 1), (2, 1), (1, 4)):
        with pytest.raises(ValueError):
            page_range(given, first, last)


def test_capacita_numbers_the_commentary_from_n_5():
    """run-rc --commentary-chapter 8|9 --commentary-first-section 5: after the load chapter's n.1〜n.4."""
    assert (CHAPTER_8.commentary, CHAPTER_9.commentary) == ((8, 5), (9, 5))


ALL = {"section_forces": "8.5", "bending_safety_destruction": "8.6", "shear_safety_destruction": None,
       "bending_durability": "8.7", "shear_durability": None, "bending_serviceability": "8.8",
       "bending_restorability": "8.9", "shear_restorability": None, "bending_rebar_amount": "8.10"}
ACROSS = {"section_forces": "9.5", "bending_safety_destruction": "9.6", "shear_safety_destruction": None,
          "bending_durability": "9.7", "bending_restorability": "9.8", "shear_restorability": None,
          "bending_rebar_amount": "9.9"}


def test_the_sections_referred_to_have_the_numbers_capacita_gave_them():
    _, result = check()
    assert (reference(replace(result, headings=ALL), REBAR_AMOUNT), reference(replace(result, headings=ALL), DURABILITY)) \
        == ("8.10", "8.7")
    assert reference(replace(result, headings=ACROSS), REBAR_AMOUNT) == "9.9"  # 使用性 not printed: one up
    # not numbered: no check in the same generation, not checked yet, a section not printed or without its own heading
    assert reference(None, REBAR_AMOUNT) is None and reference(result, REBAR_AMOUNT) is None
    assert reference(replace(result, headings={**ALL, REBAR_AMOUNT: None}), REBAR_AMOUNT) is None
    assert reference(replace(result, headings={"section_forces": "8.5"}), DURABILITY) is None


def test_the_foundation_check_follows_the_last_numbered_group():
    _, result = check()
    assert following_section(replace(result, headings=ALL)) == 11
    assert following_section(replace(result, headings=ACROSS)) == 10
    assert following_section(None) == following_section(result) == FOLLOWING_ALL == 11
    assert following_section(replace(result, headings=dict.fromkeys(ALL))) == FOLLOWING_ALL
