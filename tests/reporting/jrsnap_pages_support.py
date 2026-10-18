"""Stand-in JRSNAP pages for the 0710 / 0720 report tests: the データ確認図 (decision 50) and the load diagram
(decision 51).

The report takes JRSNAP's pages as they are, so a test gives it these pages (five of the データ確認図, one per figure,
and one load diagram page per basic case) and then checks the pages WebPier laid out, which are the report without
them.
"""

from __future__ import annotations

import io

import pymupdf
from reportlab.pdfgen import canvas

from webpier.reporting.stages import insertion

DATA_CHECK_MARK = "FAKE DATA CHECK"
LOAD_DIAGRAM_MARK = "FAKE JRSNAP LOAD DIAGRAM"
DATA_CHECK_PAGES = 5
LONGITUDINAL_LOAD_CASES = 8  # 0710: one load diagram page per basic case
TRANSVERSE_LOAD_CASES = 9  # 0720


def _pdf(mark: str, count: int) -> bytes:
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for number in range(1, count + 1):
        page.drawString(60, 780, f"{mark} {number}/{count}")
        page.showPage()
    page.save()
    return stream.getvalue()


DATA_CHECK = _pdf(DATA_CHECK_MARK, DATA_CHECK_PAGES)


def load_diagram(load_cases: int) -> bytes:
    """The stand-in load diagram: one page per basic case, ``FAKE JRSNAP LOAD DIAGRAM n/N``."""
    return _pdf(LOAD_DIAGRAM_MARK, load_cases)


def pages(load_cases: int) -> dict[str, bytes]:
    """The pages the report receives (StageSpec.render)."""
    return {insertion.DATA_CHECK: DATA_CHECK, insertion.LOAD_DIAGRAM: load_diagram(load_cases)}


def data_check_page(page) -> bool:
    """A pymupdf page of the stand-in データ確認図."""
    return DATA_CHECK_MARK in page.get_text()


def load_diagram_page(page) -> bool:
    """A pymupdf page of the stand-in load diagram."""
    return LOAD_DIAGRAM_MARK in page.get_text()


def inserted(page) -> bool:
    """A pymupdf page of either stand-in."""
    return data_check_page(page) or load_diagram_page(page)


def layout(units, insertions) -> list[list]:
    """The scene pages of each document the report is laid out in, in order."""
    return [list(document.layout()) for document in insertion.documents(units, insertions)]


def page_order(path, chapter: int, load_cases: int) -> None:
    """§n and n.1, the データ確認図, n.2 on a new page and the n.3 heading as the last line of its document, the load
    diagram one case a page in CASE order, then n.4 on a new page (decisions 50, 51)."""
    with pymupdf.open(path) as pdf:
        texts = [page.get_text().strip() for page in pdf]
        marks = [text if inserted(page) else None for text, page in zip(texts, pdf)]
    check = marks.index(f"FAKE DATA CHECK 1/{DATA_CHECK_PAGES}")
    diagram = marks.index(f"FAKE JRSNAP LOAD DIAGRAM 1/{load_cases}")
    assert check >= 1 and texts[0].startswith(f"§{chapter}.") and f"{chapter}.1 検討モデル" in texts[0]
    assert marks[check:check + DATA_CHECK_PAGES] == [f"FAKE DATA CHECK {n}/{DATA_CHECK_PAGES}"
                                                     for n in range(1, DATA_CHECK_PAGES + 1)]
    assert texts[check + DATA_CHECK_PAGES].startswith(f"{chapter}.2 作用の計算")
    assert texts[diagram - 1].splitlines()[-1] == f"{chapter}.3 荷重図"
    assert marks[diagram:diagram + load_cases] == [f"FAKE JRSNAP LOAD DIAGRAM {n}/{load_cases}"
                                                   for n in range(1, load_cases + 1)]
    assert texts[diagram + load_cases].startswith(f"{chapter}.4 作用の組合せ")
    webpier = [index for index, mark in enumerate(marks) if mark is None]
    assert webpier == [*range(check), *range(check + DATA_CHECK_PAGES, diagram),
                       *range(diagram + load_cases, len(texts))]
    assert "".join(texts).count(f"{chapter}.3 荷重図") == 1 and "".join(texts).count(f"{chapter}.4 作用の組合せ") == 1
