"""The grid Excel workbook of a report (GridLayoutPdf's ``render_xlsx``), published in export/ beside its PDF.

It holds the pages WebPier lays out (a stage's ``grid_documents``), all on one sheet; the pages of other programs
(FEMPython, Capacita, JRSNAP, Aggre-SE) are not in it. It is written with ``strict=True``: a piece moved from its cells
or a command written as a shape instead of the way its structure asks for raises ``XlsxStrictError`` and nothing is
written. GridLayoutPdf zips with a fixed date, so the same pages give the same bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from gridlayoutpdf import Document, ScenePage, XlsxError, XlsxResult, render_xlsx


def grid_pages(documents: Sequence[Document]) -> tuple[ScenePage, ...]:
    """The pages of *documents*, in order."""
    return tuple(page for document in documents for page in document.layout())


def write_workbook(documents: Sequence[Document], path: str | Path, sheet: str) -> XlsxResult:
    """Write the pages of *documents* strictly as the one sheet *sheet* of the workbook *path*."""
    result = render_xlsx([(sheet, grid_pages(documents))], path, strict=True)
    if len(result.sheets) != 1:  # GridLayoutPdf starts a sheet where the paper, the grid or a decoration changes
        Path(path).unlink()
        raise XlsxError(f"方眼Excel が1シートに収まりません: {[info.name for info in result.sheets]}")
    return result
