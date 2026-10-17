"""The list of report PDFs: stage order first, each labelled as this calculation's result or an older file."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from webpier.gui.pdf_catalog import PdfCatalog, PdfEntry, catalog, find_pdfs
from webpier.pipeline.stages import STAGES

STEMS = tuple(stage.stem for stage in STAGES.stages)


def touch(directory: Path, *names: str) -> list[Path]:
    directory.mkdir(exist_ok=True)
    paths = [directory / name for name in names]
    for path in paths:
        path.write_bytes(b"%PDF")
    return paths


def test_reports_come_in_stage_order_then_other_pdfs_by_name(tmp_path):
    touch(tmp_path, "b 追加.pdf", "0720_線路直角方向荷重.pdf", "0500_直接基礎.pdf", "A.pdf", "0600_上部工反力.pdf",
          "note.txt")
    (tmp_path / "dir.pdf").mkdir()
    assert [path.name for path in find_pdfs(tmp_path, STEMS)] == [
        "0500_直接基礎.pdf", "0600_上部工反力.pdf", "0720_線路直角方向荷重.pdf", "A.pdf", "b 追加.pdf"]
    assert find_pdfs(tmp_path / "missing", STEMS) == []


def test_labels_tell_this_result_from_older_files(tmp_path):
    first, second = touch(tmp_path, "0500_直接基礎.pdf", "0600_上部工反力.pdf")
    shown = catalog([first, second], {second}, selected=None)
    assert [entry.label for entry in shown.entries] == [
        "0500_直接基礎.pdf  —  既存出力／今回未計算", "0600_上部工反力.pdf  —  今回の計算結果"]
    assert shown.selected == second  # the first of this calculation
    assert catalog([first, second], set(), selected=second).selected == second
    assert catalog([first, second], set(), selected=tmp_path / "gone.pdf").selected == first
    empty = catalog([], set(), selected=first)
    assert empty.entries == () and empty.selected is None and "まだありません" in empty.message


def test_the_catalog_is_immutable():
    entry = PdfEntry(Path("a.pdf"), "a")
    with pytest.raises(FrozenInstanceError):
        entry.label = "b"
    with pytest.raises(FrozenInstanceError):
        PdfCatalog((entry,), None).message = "x"
