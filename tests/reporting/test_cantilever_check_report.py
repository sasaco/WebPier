"""The 0910 report (decision 59, ADR-0008): WebPier's headings and explanations, each followed by Capacita's pages
of its section, in the order of the beam's sections (13.3 → 13.6); the values written to the WDJ printed from the
same result; the cracking moment and ε'csd pages; the fatigue conditions; 13.6 使用性 only with the appearance check
(復旧性 then 13.7); a check Capacita skipped for zero forces keeps its heading and explanation, with the reason it is
omitted and no pages; the same bytes for the same input.

Capacita's pages are stand-ins here (one page per section, each saying which section it is), cut by their ranges as
the real report is. The expected texts follow Example2 13 pp.13-38 .. 13-65 and decision 59.
"""

from __future__ import annotations

import io
import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen import canvas

from webpier.calc.cantilever import calculate_cantilever, complete_cantilever
from webpier.calc.cantilever.check import SECTIONS, calculate_cantilever_section
from webpier.calc.cantilever.response import MaxResponse, ResponseValue
from webpier.calc.reaction import calculate_reaction
from webpier.core.printed import Precision
from webpier.inputs import parse_input
from webpier.reporting.assembly import document_bytes, page_range
from webpier.reporting.stages.cantilever_check import OMITTED, build_cantilever_check, parts, render_cantilever_check

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
MARK = "FAKE CAPACITA"
KH = Precision(3, "")
HEADINGS = {"bending_safety_destruction": "13.3 安全性（破壊）の照査", "shear_safety_destruction": "(2) せん断に対する照査",
            "torsion_safety_destruction": "(3) ねじりモーメントに対する検討",
            "bending_safety_fatigue": "13.4 安全性（疲労破壊）の照査", "shear_safety_fatigue": "(2) せん断に対する照査",
            "bending_durability": "13.5 耐久性の照査", "shear_durability": "(2) せん断ひび割れの検討",
            "torsion_durability": "(3) ねじりひび割れの検討", "bending_restorability": "13.6 復旧性の照査",
            "shear_restorability": "2) せん断に対する照査", "torsion_restorability": "3) ねじりモーメントに対する検討",
            "bending_restorability_eq": "(2) 地震時の照査", "shear_restorability_eq": "2) せん断に対する照査",
            "torsion_restorability_eq": "3) ねじりモーメントに対する検討"}


def response(file: str, kh: float) -> MaxResponse:
    adopted = ResponseValue(1, "Case1", "安全性", KH(kh))
    return MaxResponse(file, (ResponseValue(1, "Case1", "復旧性", KH(kh - 0.001)), adopted), adopted)


def check(**conditions):
    data = deepcopy(CURRENT)
    data["片持ち梁の照査"] |= conditions
    pier = parse_input(data)
    reaction = calculate_reaction(pier)
    basis = calculate_cantilever(pier, reaction)
    result = complete_cantilever(pier, reaction, basis, response("線路方向_Aggre-SE.xlsx", 0.386),
                                 response("線路直角方向_Aggre-SE.xlsx", 0.571))
    return pier, calculate_cantilever_section(pier, result)


def capacita(sections, skipped=()) -> dict[str, bytes]:
    """The pages the report receives: one page per section saying its id; a skipped one is not in it."""
    stream, ranges, number = io.BytesIO(), {}, 0
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for section in sections:
        if section in skipped:
            continue
        number += 1
        ranges[section] = (number, number)
        page.drawString(60, 780, f"{MARK} {section} 1")
        page.showPage()
    page.save()
    pdf = stream.getvalue()
    return {section: page_range(pdf, *found) for section, found in ranges.items()}


def render(tmp_path: Path, *, skipped=(), **conditions) -> list[str]:
    pier, result = check(**conditions)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = render_cantilever_check(result, pier, tmp_path / "report.pdf", capacita(result.sections, skipped))
    with pymupdf.open(path) as document:
        return [page.get_text() for page in document]


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> list[str]:
    return render(tmp_path_factory.mktemp("cantilever-check"))


@pytest.fixture(scope="module")
def with_appearance(tmp_path_factory) -> list[str]:
    return render(tmp_path_factory.mktemp("cantilever-check-appearance"), skipped=("torsion_durability",), 外観の照査="行う")


def webpier_pages(pages: list[str]) -> str:
    return "\n".join(text for text in pages if MARK not in text)


def flat(pages: list[str]) -> str:
    """WebPier's text without spaces and line breaks (a long line wraps where the layout decides)."""
    return webpier_pages(pages).replace(" ", "").replace("　", "").replace("\n", "")


def sections_of(pages: list[str]) -> list[str]:
    return [text.split()[2] for text in pages if MARK in text]


def test_each_section_follows_its_heading_in_report_order(pages):
    expected = [section for section in SECTIONS if section != "bending_serviceability"]
    assert sections_of(pages) == expected
    order = [text.split()[2] if MARK in text else None for text in pages]
    for section, heading in HEADINGS.items():
        first = order.index(section)
        assert MARK not in pages[first - 1], section
        assert heading in "\n".join(pages[:first]).rsplit(MARK, 1)[-1], section
    text = webpier_pages(pages)
    assert "13. 片持ち梁" not in text and "使用性の照査" not in text
    assert not any(reason in text.replace("\n", "") for reason in OMITTED.values())


def test_the_values_written_to_the_wdj_are_printed(pages):
    text = flat(pages)
    for printed in ("構造物係数(=1.2)", "部材係数(=1.1)", "構造物係数(=1.1)", "部材係数(=1.0)", "構造物係数(=1.0)",
                    "(=0.85)", "(=0.5)", "(=300×10⁻⁶)", "上面「腐食性環境」", "下面「一般の環境」", "側面「腐食性環境」"):
        assert printed in text, printed


def test_the_fatigue_conditions_of_the_input_are_printed_without_the_external_programs_work(pages):
    text = flat(pages)
    for printed in ("旅客列車→60本/日", "貨物列車→0本/日", "設計耐用年数(=100年)", "10.39", "k=0.06", "k=0.12",
                    "(=1.00)", "ΣN=365・T・{jA・NA・(SA/SC)^(1/k)+jB・NB・(SB/SC)^(1/k)}"):
        assert printed in text, printed
    assert "22754" not in text and "22.754" not in text  # ΣN is Capacita's (decision 59)
    assert text.count("列車本数") == 2  # 1) of the bending check, 2) of the shear check


def test_the_cracking_moment_and_ecsd_pages(pages):
    text = flat(pages)
    for printed in ("Mcrd=σcrd・I/y+N'd・I/(A・y)", "4.43E+12mm⁴", "y=h/2=1350mm", "=542mm", "=0.0877N/mm",
                    "Ec=26.5kN/mm²", "=2.07N/mm²", "∴σcrd=1.04×1.00×2.07=2.15N/mm²", "=7055.19kN・m",
                    "Md=373.96kN・m", "30日", "450", "100日", "350", "200日以上", "300",
                    "よって，ε'csd=300×10⁻⁶をひび割れの照査に用いる（ひび割れ発生材齢200日以上）．"):
        assert printed in text, printed
    for action in ("部材自重", "永久作用", "永久作用および変動作用"):
        assert action in text


def test_with_the_appearance_check_13_6_is_serviceability_and_restorability_13_7(with_appearance):
    assert "bending_serviceability" in sections_of(with_appearance)
    text = webpier_pages(with_appearance)
    assert "13.6 使用性の照査" in text and "13.7 復旧性の照査" in text and "13.6 復旧性" not in text
    assert "外観に対するひび割れ幅の制限値" in text


def test_a_skipped_check_keeps_its_heading_and_says_why_it_is_omitted(with_appearance):
    assert "torsion_durability" not in sections_of(with_appearance)
    text = webpier_pages(with_appearance)
    torsion = text.split("(3) ねじりひび割れの検討")[1].split("13.6 使用性の照査")[0]
    assert torsion.strip().endswith(OMITTED["torsion_durability"])
    assert set(OMITTED) == set(SECTIONS)


def test_parts_and_documents_are_one_per_section():
    _, result = check()
    found = parts(result, skipped=("shear_restorability_eq",))
    assert [section for _, section in found] == list(result.sections)
    assert found[-2][0][-1].key == "0910/shear_restorability_eq.omitted"
    documents = build_cantilever_check(result, skipped=("shear_restorability_eq",))
    assert len(documents) == len(result.sections)
    assert len({unit.key for part, _ in found for unit in part}) == sum(len(part) for part, _ in found)


def test_webpier_pages_are_the_same_bytes_for_the_same_input():
    _, result = check()
    first, second = (tuple(document_bytes(document) for document in build_cantilever_check(result)) for _ in range(2))
    assert first == second
