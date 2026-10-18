"""The parts of a report with the pages of another program in it (decisions 44, 48, 50, 51; ADR-0005).

``document_bytes`` lays out one of WebPier's documents, ``join`` writes the documents and the other program's pages
in order as one PDF, and ``page_range`` cuts pages out of another program's report. Where the pages go is
``stages.insertion``. pypdf writes the pages in order. It adds no date and its file identifier is a checksum of the
content, so the same parts give the same bytes. No page is numbered (the reference prints none).
"""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
import os
from pathlib import Path
import tempfile

from gridlayoutpdf import Document
from pypdf import PdfReader, PdfWriter


def document_bytes(document: Document) -> bytes:
    """The PDF of *document*, laid out completely and without a date."""
    with tempfile.TemporaryDirectory(prefix="webpier-part-") as directory:
        return document.render(Path(directory) / "part.pdf", invariant=True).read_bytes()


def join(parts: Sequence[bytes], path: str | Path) -> Path:
    """Write the pages of *parts*, in order, as one PDF at *path* (replaced atomically)."""
    writer = PdfWriter()
    for part in parts:
        for page in PdfReader(BytesIO(part), strict=True).pages:
            writer.add_page(page)
    destination = Path(path)
    stream = BytesIO()
    writer.write(stream)
    descriptor, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(stream.getvalue())
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return destination


def page_range(pdf: bytes, first: int, last: int) -> bytes:
    """Pages *first*..*last* (1-based, inclusive) of *pdf*, as they are, as a PDF of their own.

    0611 and 0621 cut Capacita's report by the page range of each section (decision 48).
    """
    reader = PdfReader(BytesIO(pdf), strict=True)
    if not 1 <= first <= last <= len(reader.pages):
        raise ValueError(f"pages {first}..{last} are not in a PDF of {len(reader.pages)} pages")
    writer = PdfWriter()
    for page in reader.pages[first - 1:last]:
        writer.add_page(page)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()
