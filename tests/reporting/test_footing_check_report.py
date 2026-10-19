"""The 0810 / 0820 report (decision 60, ADR-0008): WebPier's headings and explanations of 12.2〜12.4 (0810) and
12.5〜12.7 (0820), each followed by Capacita's pages of its section, in the order of the five sections asked of it;
the shear crack check is not asked of Capacita and its omission (面部材のため省略) is printed after the durability
pages, before the restorability chapter; the values written to the WDJ are printed from the same result.

Capacita's pages are stand-ins here (one page per section, each saying which section it is), cut by their ranges as
the real report is. The expected texts follow 12_フーチング.pdf 254〜266 and decision 60.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen import canvas

from footing_report_cases import footing_check
from webpier.reporting.assembly import document_bytes, page_range
from webpier.reporting.stages.footing_check import (LONGITUDINAL, TRANSVERSE, build_footing_check, parts,
                                                    render_footing_check)

MARK = "FAKE CAPACITA"
SECTIONS = ("bending_safety_destruction", "shear_safety_destruction", "bending_durability",
            "bending_restorability_eq", "shear_restorability_eq")
# The headings of WebPier's part before each section, in order (0810).
HEADINGS = {"bending_safety_destruction": ("12.2 安全性の照査", "1) 曲げモーメントと軸方向力に対する照査"),
            "shear_safety_destruction": ("2) せん断力に対する照査",),
            "bending_durability": ("12.3 耐久性の照査", "1) 曲げモーメントと軸方向力に対する照査"),
            "bending_restorability_eq": ("2) せん断ひび割れの検討", "12.4 復旧性（地震時）の照査",
                                         "1) 曲げモーメントと軸方向力に対する照査"),
            "shear_restorability_eq": ("2) せん断力に対する照査",)}
OMISSION = ("本構造物のフーチングは，ディープビーム的な耐荷機構を有する面部材である．このため，せん断補強鋼材の役割が通常の"
            "棒部材と異なり，さらにひび割れ性状も異なると考えられる．したがって，せん断力によって耐久性に問題を生じることは"
            "少ないと考え，検討を省略する．")


def capacita_report(sections) -> tuple[bytes, dict]:
    """A stand-in Capacita report and the page range of each section: one page per section."""
    stream, ranges = io.BytesIO(), {}
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for number, section in enumerate(sections, 1):
        ranges[section] = (number, number)
        page.drawString(60, 780, f"{MARK} {section} 1")
        page.showPage()
    page.save()
    return stream.getvalue(), ranges


def capacita(sections) -> dict[str, bytes]:
    pdf, ranges = capacita_report(sections)
    return {section: page_range(pdf, *found) for section, found in ranges.items()}


def render(tmp_path: Path, *, transverse=False, **conditions) -> list[str]:
    _, check = footing_check("0800_transverse" if transverse else "0800_longitudinal", **conditions)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = render_footing_check(check, tmp_path / "report.pdf", capacita(check.sections),
                                TRANSVERSE if transverse else LONGITUDINAL)
    with pymupdf.open(path) as document:
        return [page.get_text() for page in document]


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> list[str]:
    return render(tmp_path_factory.mktemp("footing-check"))


@pytest.fixture(scope="module")
def across(tmp_path_factory) -> list[str]:
    return render(tmp_path_factory.mktemp("footing-check-across"), transverse=True)


def webpier_pages(pages: list[str]) -> str:
    return "\n".join(text for text in pages if MARK not in text)


def order_of(pages: list[str]) -> list[str | None]:
    return [text.split()[2] if MARK in text else None for text in pages]


def test_each_section_follows_its_headings_in_report_order(pages):
    order = order_of(pages)
    assert [section for section in order if section] == list(SECTIONS)
    for section, headings in HEADINGS.items():
        first = order.index(section)
        assert MARK not in pages[first - 1], section
        before = "\n".join(pages[:first]).rsplit(MARK, 1)[-1]
        positions = [before.index(heading) for heading in headings]
        assert positions == sorted(positions), section
    assert pages[0].strip().startswith("12.2 安全性の照査")
    assert order[-1] == "shear_restorability_eq"


def test_the_shear_crack_omission_follows_the_durability_pages(pages):
    order = order_of(pages)
    following = pages[order.index("bending_durability") + 1]
    assert MARK not in following and following.strip().startswith("2) せん断ひび割れの検討")
    text = following.replace("\n", "")
    assert OMISSION in text
    assert text.index("検討を省略する．") < text.index("12.4 復旧性（地震時）の照査")


def test_across_the_track_the_sections_are_numbered_12_5_to_12_7(across):
    text = webpier_pages(across)
    for heading in ("12.5 安全性の照査", "12.6 耐久性の照査", "12.7 復旧性（地震時）の照査"):
        assert heading in text, heading
    assert not any(number in text for number in ("12.2", "12.3", "12.4"))
    assert [section for section in order_of(across) if section] == list(SECTIONS)


def test_the_values_written_to_the_wdj_are_printed(pages):
    text = webpier_pages(pages).replace(" ", "")
    for printed in ("構造物係数(=1.2)", "部材係数(=1.1)", "構造物係数(=1.0)", "(=0.85)", "(=300×10⁻⁶)",
                    "部材係数(=1.0)", "「一般の環境」"):
        assert printed in text, printed


def test_the_values_only_capacita_holds_are_not_printed(pages):
    """RC標準's tables and formulas Capacita evaluates (σsl1 140/120/100, Wlim 0.005c, fvcd ≧ 0.72, fwcd ≧ 7.8, γc)."""
    text = webpier_pages(pages)
    for absent in ("腐食性環境", "0.005c", "140", "0.72", "7.8", "γc＝1.3", "1.15"):
        assert absent not in text, absent


def test_the_flowchart_writes_the_decision_correctly(pages):
    text = webpier_pages(pages)
    for printed in ("START", "σb ≦ σbl", "Yes", "No", "γi・Wd / Wlim ≦ 1.0"):
        assert printed in text, printed


def test_the_seismic_restorability_prints_its_own_factors(pages):
    """RC標準 復旧性（損傷）地震時: γi 1.0 and γb 1.0 for bending (12_フーチング.pdf 263), γb of Vsd 1.0."""
    text = webpier_pages(pages).split("12.4 復旧性（地震時）の照査")[1].replace(" ", "")
    assert "構造物係数(=1.0)" in text and "部材係数(=1.0)" in text and "構造物係数(=1.2)" not in text


def test_webpier_pages_are_the_same_bytes_for_the_same_input():
    _, check = footing_check()
    first = [document_bytes(document) for document in build_footing_check(check, LONGITUDINAL)]
    assert len(first) == len(parts(check, LONGITUDINAL)) == 5
    assert [document_bytes(document) for document in build_footing_check(footing_check()[1], LONGITUDINAL)] == first


def test_the_report_is_the_same_bytes_for_the_same_pages(tmp_path):
    _, check = footing_check()
    given = capacita(check.sections)
    one = render_footing_check(check, tmp_path / "one.pdf", given, LONGITUDINAL).read_bytes()
    two = render_footing_check(check, tmp_path / "two.pdf", given, LONGITUDINAL).read_bytes()
    assert one == two


@pytest.mark.parametrize("section", SECTIONS)
def test_every_section_must_have_its_pages(tmp_path, section):
    _, check = footing_check()
    given = {name: found for name, found in capacita(check.sections).items() if name != section}
    with pytest.raises(ValueError, match=f"差し込むページ {section} がありません"):
        render_footing_check(check, tmp_path / "report.pdf", given, LONGITUDINAL)
    assert not (tmp_path / "report.pdf").exists()
