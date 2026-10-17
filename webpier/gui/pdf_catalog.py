"""The PDFs shown by the preview: the reports in stage order, then any other PDF of the output directory.

Each is labelled as a result of the calculation just verified, or as an older file that this calculation did not
produce; the preview never presents an old report as current.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

CURRENT = "今回の計算結果"
OLD = "既存出力／今回未計算"
EMPTY = "PDFはまだありません。「保存して計算・PDF出力」で作成します。"


@dataclass(frozen=True)
class PdfEntry:
    path: Path
    label: str


@dataclass(frozen=True)
class PdfCatalog:
    entries: tuple[PdfEntry, ...]
    selected: Path | None
    message: str = ""


def find_pdfs(directory: Path, stems: Sequence[str]) -> list[Path]:
    """Regular PDF files of *directory*: the report stems in order, then the others by name."""
    if not directory.is_dir():
        return []
    found = [path for path in directory.glob("*.pdf") if path.is_file() and not path.is_symlink()]
    return sorted(found, key=lambda path: (stems.index(path.stem), "") if path.stem in stems
                  else (len(stems), path.name.casefold()))


def catalog(paths: Sequence[Path], current: Collection[Path], *, selected: Path | None,
            message: str = "") -> PdfCatalog:
    """Label *paths*; keep *selected* if it is still listed, else the first current report, else the first."""
    entries = tuple(PdfEntry(path, f"{path.name}  —  {CURRENT if path in current else OLD}") for path in paths)
    if not entries:
        return PdfCatalog((), None, message or EMPTY)
    if selected not in paths:
        selected = next((path for path in paths if path in current), paths[0])
    return PdfCatalog(entries, selected, message)
