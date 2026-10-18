"""Stand-in load diagram pages for the 0610 / 0620 report tests (decision 44).

The report takes FEMPython's pages as they are, so a test gives it these two pages and then checks the pages
WebPier laid out, which are the report without them.
"""

from __future__ import annotations

import io

from reportlab.pdfgen import canvas

from webpier.reporting.stages import insertion
from webpier.reporting.stages.insertion import DIAGRAMS, Insertion

MARK = "FAKE LOAD DIAGRAM"
PAGES = 2


def _pdf() -> bytes:
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for number in range(1, PAGES + 1):
        page.drawString(60, 780, f"{MARK} {number}/{PAGES}")
        page.showPage()
    page.save()
    return stream.getvalue()


LOAD_DIAGRAM = _pdf()
REPORT = {insertion.LOAD_DIAGRAM: LOAD_DIAGRAM}  # the pages the report receives (StageSpec.render)


def inserted(page) -> bool:
    """A pymupdf page of the stand-in load diagram."""
    return MARK in page.get_text()


def report_pages(pdf) -> list:
    """The pages WebPier laid out: the report without the load diagram pages."""
    return [page for page in pdf if not inserted(page)]


def layout(units, prefix: str) -> tuple[list, list]:
    """The scene pages of the two documents the report is laid out in (before and after the load diagrams)."""
    before, after = insertion.documents(units, (Insertion(insertion.LOAD_DIAGRAM, prefix + DIAGRAMS),))
    return list(before.layout()), list(after.layout())
