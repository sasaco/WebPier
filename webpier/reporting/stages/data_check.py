"""The データ確認図 pages of 0710 (after 10.1) and 0720 (after 11.1): JRSNAP's pages in the report (decision 50).

The manuscript is laid out as two documents split before the actions heading (10.2, 11.2): the model ends the
first document, JRSNAP's pages follow as they are, and the actions start the second document on a new page. As in
the reference (Example2 10-3..10-7), WebPier puts no heading or text of its own before them; each page carries
JRSNAP's own title and header.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gridlayoutpdf import Document

from ..assembly import render_with_pages
from .frame_report import Unit, document


def documents(units: Sequence[Unit], key: str) -> tuple[Document, Document]:
    """The manuscript *units* before the unit *key* (the actions heading), and from it."""
    split = [unit.key for unit in units].index(key)
    return document(units[:split]), document(units[split:])


def render(units: Sequence[Unit], key: str, pages: bytes, path: str | Path) -> Path:
    """The report of *units* with *pages* before the unit *key*."""
    before, after = documents(units, key)
    return render_with_pages(before, pages, after, path)
