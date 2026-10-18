"""Pages of other programs in a report (decisions 44, 48, 50, 51): the manuscript is split where each insertion says,
the pages go between the documents as they are, each document after an insertion starts on a new page, and a document
that ends with a heading ends with it as its last line. Small manuscripts and stand-in pages, not a stage's."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen import canvas

from webpier.reporting.stages.frame_report import Manuscript
from webpier.reporting.stages.insertion import DIAGRAMS, Insertion, diagrams_heading, documents, render_with_pages


def stand_in(mark: str, count: int) -> bytes:
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for number in range(1, count + 1):
        page.drawString(60, 780, f"{mark} {number}/{count}")
        page.showPage()
    page.save()
    return stream.getvalue()


FIRST = stand_in("FAKE FIRST", 2)
SECOND = stand_in("FAKE SECOND", 1)


def manuscript():
    """1.1 the model, 1.2 the actions, 1.3 the load diagram heading, 1.4 the combinations."""
    m = Manuscript("t/")
    m.heading("model.heading", "1.1 検討モデル", 1)
    m.paragraph("model.text", "モデルの本文")
    m.heading("actions.heading", "1.2 作用の計算", 1)
    m.paragraph("actions.text", "作用の本文")
    diagrams_heading(m, "1.3 荷重図")
    m.heading("combination.heading", "1.4 作用の組合せ", 1)
    m.paragraph("combination.text", "組合せの本文")
    return tuple(m.units)


AFTER_HEADING = Insertion("second", "t/" + DIAGRAMS)
BEFORE_ACTIONS = Insertion("first", "t/actions.heading", before=True)


def texts(path: Path) -> list[str]:
    with pymupdf.open(path) as pdf:
        return [page.get_text().strip() for page in pdf]


def font(path: Path, page: int, text: str) -> str:
    with pymupdf.open(path) as pdf:
        spans = [span for block in pdf[page].get_text("dict")["blocks"] for line in block.get("lines", ())
                 for span in line["spans"] if span["text"].strip() == text]
    assert spans, text
    return spans[0]["font"]


def test_one_insertion_after_a_heading_ends_the_document_with_the_heading(tmp_path: Path):
    path = render_with_pages(manuscript(), (AFTER_HEADING,), {"second": SECOND}, tmp_path / "r.pdf")
    pages = texts(path)
    assert len(pages) == 3
    assert pages[0].startswith("1.1 検討モデル") and pages[0].splitlines()[-1] == "1.3 荷重図"
    assert font(path, 0, "1.3 荷重図") == font(path, 0, "1.2 作用の計算")  # set in the heading style
    assert pages[1] == "FAKE SECOND 1/1"
    assert pages[2].startswith("1.4 作用の組合せ") and pages[2].endswith("組合せの本文")
    assert list(tmp_path.iterdir()) == [path]
    found = documents(manuscript(), (AFTER_HEADING,))
    assert len(found) == 2 and all(len(document.layout()) == 1 for document in found)


def test_two_insertions_go_in_manuscript_order(tmp_path: Path):
    path = render_with_pages(manuscript(), (BEFORE_ACTIONS, AFTER_HEADING), {"first": FIRST, "second": SECOND},
                             tmp_path / "r.pdf")
    pages = texts(path)
    assert [page.splitlines()[0] for page in pages] == ["1.1 検討モデル", "FAKE FIRST 1/2", "FAKE FIRST 2/2",
                                                        "1.2 作用の計算", "FAKE SECOND 1/1", "1.4 作用の組合せ"]
    assert pages[0].endswith("モデルの本文")
    assert pages[3].splitlines()[-1] == "1.3 荷重図" and "作用の本文" in pages[3]
    assert len(documents(manuscript(), (BEFORE_ACTIONS, AFTER_HEADING))) == 3


def test_an_insertion_after_the_last_unit_ends_the_report_with_the_pages(tmp_path: Path):
    units = manuscript()[:5]  # up to 1.3 荷重図
    path = render_with_pages(units, (AFTER_HEADING,), {"second": SECOND}, tmp_path / "r.pdf")
    pages = texts(path)
    assert len(pages) == 2 and pages[0].splitlines()[-1] == "1.3 荷重図" and pages[1] == "FAKE SECOND 1/1"
    assert len(documents(units, (AFTER_HEADING,))) == 1


def test_an_optional_insertion_without_pages_puts_nothing_in_but_still_starts_a_new_page(tmp_path: Path):
    optional = Insertion("first", "t/actions.heading", before=True, optional=True)
    path = render_with_pages(manuscript(), (optional, AFTER_HEADING), {"second": SECOND}, tmp_path / "r.pdf")
    assert [page.splitlines()[0] for page in texts(path)] == ["1.1 検討モデル", "1.2 作用の計算", "FAKE SECOND 1/1",
                                                              "1.4 作用の組合せ"]


@pytest.mark.parametrize(("insertions", "pages", "message"), [
    ((AFTER_HEADING,), {}, "差し込むページ second がありません"),
    ((AFTER_HEADING,), {"second": SECOND, "first": FIRST}, "差し込む場所のないページがあります: first"),
    ((AFTER_HEADING, BEFORE_ACTIONS), {"first": FIRST, "second": SECOND}, "差し込む位置が原稿の順になっていません"),
    ((Insertion("first", "t/model.text"), Insertion("second", "t/actions.heading", before=True)),
     {"first": FIRST, "second": SECOND}, "差し込む位置が原稿の順になっていません"),  # the same place twice
    ((Insertion("first", "t/model.heading", before=True),), {"first": FIRST}, "差し込む位置が原稿の順になっていません"),
    ((Insertion("first", "t/missing"),), {"first": FIRST}, "差し込む位置の単位 t/missing がありません"),
    ((Insertion("first", "t/model.text"), Insertion("first", "t/actions.text")), {"first": FIRST},
     "差し込むページの名前が重複しています"),
])
def test_a_wrong_insertion_is_an_error_and_writes_nothing(tmp_path: Path, insertions, pages, message):
    with pytest.raises(ValueError, match=message):
        render_with_pages(manuscript(), insertions, pages, tmp_path / "r.pdf")
    assert list(tmp_path.iterdir()) == []


def test_units_with_the_same_key_are_an_error(tmp_path: Path):
    units = manuscript()
    with pytest.raises(ValueError, match="帳票の単位に重複したキーがあります"):
        documents((*units, units[1]), (AFTER_HEADING,))


def test_the_same_input_gives_the_same_bytes(tmp_path: Path):
    insertions, pages = (BEFORE_ACTIONS, AFTER_HEADING), {"first": FIRST, "second": SECOND}
    first = render_with_pages(manuscript(), insertions, pages, tmp_path / "a.pdf").read_bytes()
    assert render_with_pages(manuscript(), insertions, pages, tmp_path / "b.pdf").read_bytes() == first
