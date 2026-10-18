"""A report with another program's pages between its parts (decision 44): order, no date, the same bytes."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from load_diagram_support import LOAD_DIAGRAM, MARK, PAGES
from webpier.reporting.assembly import document_bytes, join, render_with_pages
from webpier.reporting.document import paragraph, report


def texts(data: bytes) -> list[str]:
    return [page.extract_text().strip() for page in PdfReader(BytesIO(data)).pages]


def test_the_pages_go_between_the_parts_as_they_are(tmp_path: Path):
    path = render_with_pages(report(paragraph("前半")), LOAD_DIAGRAM, report(paragraph("後半")), tmp_path / "r.pdf")
    assert texts(path.read_bytes()) == ["前半", *(f"{MARK} {n}/{PAGES}" for n in range(1, PAGES + 1)), "後半"]
    assert list(tmp_path.iterdir()) == [path]


def test_the_join_adds_no_date_and_gives_the_same_bytes(tmp_path: Path):
    parts = (document_bytes(report(paragraph("前半"))), LOAD_DIAGRAM)
    first = join(parts, tmp_path / "a.pdf").read_bytes()
    assert join(parts, tmp_path / "b.pdf").read_bytes() == first
    assert b"CreationDate" not in first and b"ModDate" not in first


def test_an_unreadable_part_leaves_the_destination(tmp_path: Path):
    path = tmp_path / "r.pdf"
    path.write_bytes(b"previous")
    with pytest.raises(PdfReadError):
        join((LOAD_DIAGRAM, b"%PDF-1.4 broken"), path)
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]


def test_a_failed_write_removes_its_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from webpier.reporting import assembly

    def refuse(source, destination):
        raise PermissionError("locked")

    monkeypatch.setattr(assembly.os, "replace", refuse)
    with pytest.raises(PermissionError):
        join((LOAD_DIAGRAM,), tmp_path / "r.pdf")
    assert list(tmp_path.iterdir()) == []
