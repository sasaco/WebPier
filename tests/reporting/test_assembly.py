"""The parts of a report with another program's pages in it (decision 44): the join adds no date and gives the same
bytes, and replaces its destination atomically. Where the pages go is tested in test_insertion."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf.errors import PdfReadError

from load_diagram_support import LOAD_DIAGRAM
from webpier.reporting.assembly import document_bytes, join
from webpier.reporting.document import paragraph, report


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
