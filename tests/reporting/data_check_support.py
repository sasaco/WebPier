"""Stand-in データ確認図 pages for the 0710 / 0720 report tests (decision 50).

The report takes JRSNAP's pages as they are, so a test gives it these five pages (one per figure) and then checks
the pages WebPier laid out, which are the report without them.
"""

from __future__ import annotations

import io

from reportlab.pdfgen import canvas

from webpier.reporting.stages import data_check

MARK = "FAKE DATA CHECK"
PAGES = 5


def _pdf() -> bytes:
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(595, 842), invariant=1)
    for number in range(1, PAGES + 1):
        page.drawString(60, 780, f"{MARK} {number}/{PAGES}")
        page.showPage()
    page.save()
    return stream.getvalue()


DATA_CHECK = _pdf()


def inserted(page) -> bool:
    """A pymupdf page of the stand-in データ確認図."""
    return MARK in page.get_text()


def layout(units, key: str) -> tuple[list, list]:
    """The scene pages of the two documents the report is laid out in (before and after the データ確認図)."""
    before, after = data_check.documents(units, key)
    return list(before.layout()), list(after.layout())
