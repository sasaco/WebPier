"""The load diagram section of 0610 (8.3) and 0620 (9.3): a heading, then FEMPython's pages (decision 44).

The manuscript is laid out as two documents split after the heading: the heading stays in the flow (it may end
the last page of the previous section), FEMPython's pages follow as they are, and the next section (the
combinations) starts the second document on a new page. The section has no text of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gridlayoutpdf import Document

from ..assembly import render_with_pages
from ..document import blank, paragraph, report
from ..styles import HEADING as HEADING_STYLE
from .frame_report import Manuscript, Unit, blocks, document

HEADING = "diagrams.heading"


def heading(m: Manuscript, title: str) -> None:
    m.heading(HEADING, title, 1)


def documents(units: Sequence[Unit], prefix: str) -> tuple[Document, Document]:
    """The manuscript *units* up to the load diagram heading, and from the section after it."""
    keys = [unit.key for unit in units]
    split = keys.index(prefix + HEADING)
    title = units[split]
    before = blocks(units[:split])
    # The heading ends its document and FEMPython's pages are what it heads, so it is set as a line in the
    # heading style: a GridLayoutPdf Heading must stay with a next block of its own document.
    blank(before)
    before.append(paragraph(title.value, left=title.left, style=HEADING_STYLE, block_id=title.key,
                            min_first=1, min_last=1))
    return report(*before), document(units[split + 1:])


def render(units: Sequence[Unit], prefix: str, pages: bytes, path: str | Path) -> Path:
    """The report of *units* with *pages* after the load diagram heading."""
    before, after = documents(units, prefix)
    return render_with_pages(before, pages, after, path)
