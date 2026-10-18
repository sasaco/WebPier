"""The 0611 / 0621 report (decision 48, ADR-0008): WebPier's headings and explanations, each followed by Capacita's
pages of its section, in the order n.5 → n.9 (8 along the track, 9 across it); the values written to the WDJ printed
from the same result; no n.8 without the appearance check; a check Capacita skipped for zero forces keeps its heading
and explanation, with the reason it is omitted and no pages.

Capacita's pages are stand-ins here (one page per section, each saying which section it is), cut by their ranges as
the real report is. The expected texts follow Example2 08 pp.8-14 .. 8-25, 09 pp.9-16 .. 9-23 and decision 48.
"""

from __future__ import annotations

import io
import json
from copy import deepcopy
from dataclasses import dataclass
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
from webpier.reporting.assembly import document_bytes, page_range
from webpier.reporting.stages.column_check import LONGITUDINAL as CHAPTER_8, TRANSVERSE as CHAPTER_9
from webpier.reporting.stages.column_check import OMITTED, build_column_check, parts, render_column_check

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
MARK = "FAKE CAPACITA"
HEADINGS = {"section_forces": "8.5 断面力の総括", "bending_safety_destruction": "8.6 安全性（破壊）の照査",
            "shear_safety_destruction": "(2) せん断に対する照査", "bending_durability": "8.7 耐久性の照査",
            "shear_durability": "(2) せん断ひび割れの検討", "bending_serviceability": "8.8 使用性の照査",
            "bending_restorability": "8.9 復旧性の照査", "shear_restorability": "(2) せん断に対する照査"}
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


@dataclass(frozen=True)
class Pages:
    """Stand-in Capacita pages: section_forces has two pages, every other section one; none for a skipped one."""

    pdf: bytes
    ranges: dict
    skipped: tuple[str, ...] = ()

    def section(self, section_id):
        return None if section_id in self.skipped else self.ranges[section_id]


def capacita(sections, skipped=()) -> Pages:
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
    return Pages(stream.getvalue(), ranges, tuple(skipped))


def render(tmp_path: Path, *, transverse=False, skipped=(), **conditions) -> list[str]:
    pier, result = check(transverse=transverse, **conditions)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = render_column_check(result, pier, tmp_path / "report.pdf", capacita(result.sections, skipped),
                               CHAPTER_9 if transverse else CHAPTER_8)
    with pymupdf.open(path) as document:
        return [page.get_text() for page in document]


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> list[str]:
    return render(tmp_path_factory.mktemp("column-check"))


@pytest.fixture(scope="module")
def across(tmp_path_factory) -> list[str]:
    return render(tmp_path_factory.mktemp("column-check-across"), transverse=True, skipped=SKIPPED)


def webpier_pages(pages: list[str]) -> str:
    return "\n".join(text for text in pages if MARK not in text)


def test_each_section_follows_its_heading_in_report_order(pages):
    order = [text.split()[2] if MARK in text else None for text in pages]
    sections = [section for section in order if section]
    assert sections == ["section_forces", "section_forces", "bending_safety_destruction", "shear_safety_destruction",
                        "bending_durability", "shear_durability", "bending_serviceability", "bending_restorability",
                        "shear_restorability"]
    for section, heading in HEADINGS.items():
        first = order.index(section)
        before = pages[first - 1]
        assert MARK not in before, section
        assert heading in "\n".join(pages[:first]).rsplit(MARK, 1)[-1], section
    assert pages[0].strip().startswith("8.5 断面力の総括") and MARK in pages[1]
    text = webpier_pages(pages).replace("\n", "")
    assert not any(reason in text for reason in OMITTED.values())  # nothing skipped along the track


def test_across_the_track_the_sections_are_numbered_9(across):
    text = webpier_pages(across)
    for heading in HEADINGS.values():
        assert heading.replace("8.", "9.", 1) in text, heading
    assert across[0].strip().startswith("9.5 断面力の総括") and "8." not in text.replace("0.85", "")


def test_a_skipped_check_keeps_its_explanation_and_says_why_it_is_omitted(across):
    """Example2 across the track (09 notes): no Capacita pages for 9.7 (2) and 9.8; the reasons follow their
    explanations, and the next part starts after them."""
    order = [text.split()[2] if MARK in text else None for text in across]
    assert [section for section in order if section] == [
        "section_forces", "section_forces", "bending_safety_destruction", "shear_safety_destruction",
        "bending_durability", "bending_restorability", "shear_restorability"]
    text = webpier_pages(across)
    shear = text.split("(2) せん断ひび割れの検討")[1].split("9.8 使用性の照査")[0]
    assert "σsl2 ：永久作用による鉄筋応力度の制限値" in shear.replace(" :", " ：")
    assert shear.rstrip().endswith("永久作用と変動作用によるせん断力が生じないため，せん断ひび割れの検討を省略する．")
    serviceability = text.split("9.8 使用性の照査")[1].split("9.9 復旧性の照査")[0].replace("\n", "")
    assert "外観に対するひび割れ幅の制限値" in serviceability
    assert serviceability.rstrip().endswith(
        "永久作用による曲げモーメントおよび引張の軸方向力が生じないため，外観に対する曲げひび割れの検討を省略する．")


def test_the_values_written_to_the_wdj_are_printed(pages):
    text = webpier_pages(pages).replace(" ", "")
    for printed in ("構造物係数(=1.2)", "部材係数(=1.1)", "構造物係数(=1.0)", "(=0.85)", "(=0.5)", "(=300×10⁻⁶)",
                    "部材係数(=1.0)", "「一般の環境」"):
        assert printed in text, printed


def test_the_flowchart_writes_the_decision_correctly(pages):
    text = webpier_pages(pages)
    for printed in ("START", "σb ≦ σbl", "Yes", "No", "γi・Wd / Wlim ≦ 1.0"):
        assert printed in text, printed


def test_the_values_only_capacita_holds_are_not_printed(pages):
    """RC標準's tables (σsl1 140/120/100, σsl2, Wlim 0.005c...), σbl, k2's coefficients, z = d/1.15, γb of Vcd."""
    text = webpier_pages(pages)
    for absent in ("腐食性環境", "0.005c", "140", "1.15", "15/(f'cd+20)", "0.30", "γbは1.3"):
        assert absent not in text, absent


def test_restorability_prints_the_structure_factor_of_the_body(tmp_path):
    def restorability(text, number="8"):
        return text.split(f"{number}.9 復旧性の照査")[1].replace(" ", "")

    assert "構造物係数(=1.2)" in restorability(webpier_pages(render(tmp_path)))
    assert "構造物係数(=1.0)" in restorability(webpier_pages(render(tmp_path / "jr", 適用基準の機関="JR東日本")))
    assert "構造物係数(=1.2)" in restorability(webpier_pages(render(tmp_path / "across", transverse=True)), "9")


def test_without_the_appearance_check_there_is_no_8_8(tmp_path):
    pages = render(tmp_path, 外観の照査="行わない")
    text = "\n".join(pages)
    assert "8.8" not in webpier_pages(pages) and "8.9 復旧性の照査" in text
    assert "bending_serviceability" not in text


def test_webpier_pages_are_the_same_bytes_for_the_same_input():
    _, result = check()
    first = [document_bytes(document) for document in build_column_check(result, CHAPTER_8)]
    assert len(first) == len(parts(result, CHAPTER_8)) == 8
    assert [document_bytes(document) for document in build_column_check(check()[1], CHAPTER_8)] == first
    _, across = check(transverse=True)
    assert [document_bytes(document) for document in build_column_check(across, CHAPTER_9, SKIPPED)] == [
        document_bytes(document) for document in build_column_check(check(transverse=True)[1], CHAPTER_9, SKIPPED)]


def test_the_report_is_the_same_bytes_for_the_same_pages(tmp_path):
    pier, result = check()
    given = capacita(result.sections)
    one = render_column_check(result, pier, tmp_path / "one.pdf", given, CHAPTER_8).read_bytes()
    two = render_column_check(result, pier, tmp_path / "two.pdf", given, CHAPTER_8).read_bytes()
    assert one == two


def test_a_page_range_is_cut_as_it_is():
    given = capacita(["section_forces", "bending_safety_destruction"])
    with pymupdf.open(stream=page_range(given.pdf, 2, 3), filetype="pdf") as cut:
        assert [page.get_text().strip() for page in cut] == [f"{MARK} section_forces 2",
                                                            f"{MARK} bending_safety_destruction 1"]
    for first, last in ((0, 1), (2, 1), (1, 4)):
        with pytest.raises(ValueError):
            page_range(given.pdf, first, last)
