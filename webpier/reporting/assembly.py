"""A report with the pages of another program between its parts (decision 44, ADR-0005).

0610 and 0620 are laid out as two documents split after the load diagram heading; the load diagram pages that
FEMPython drew go between them as they are: pages, not a figure, so nothing is cropped, scaled or rasterized, and
their content is FEMPython's. pypdf writes the pages in order. It adds no date and its file identifier is a
checksum of the content, so the same parts give the same bytes. No page is numbered (the reference prints none).
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


def render_with_pages(before: Document, pages: bytes, after: Document, path: str | Path) -> Path:
    """*before*, then the pages of *pages* as they are, then *after* on a new page."""
    return join((document_bytes(before), pages, document_bytes(after)), path)
