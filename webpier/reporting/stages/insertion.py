"""Pages of other programs in a report (decisions 44, 48, 50, 51; ADR-0005).

A stage's manuscript is laid out as documents split where another program's pages go: FEMPython's load diagram after
8.3 / 9.3 (0610, 0620), Capacita's pages after each of n.5〜n.9 (0611, 0621), JRSNAP's データ確認図 before 10.2 / 11.2
and its load diagram after 10.3 / 11.3 (0710, 0720). The pages go between the documents as they are
(``assembly.join``): pages, not figures, so nothing is cropped, scaled or rasterized, and their content is the
program's. Each document after an insertion starts on a new page. A document that ends with a heading (8.3, 10.3,
n.5) ends with it set as a line in the heading style: the pages are what it heads, and a GridLayoutPdf Heading must
stay with a next block of its own document.

The report receives the pages by name (``StageSpec.render``): ``LOAD_DIAGRAM``, ``DATA_CHECK``, or Capacita's section
ids; the pipeline module of each program makes that mapping from the runner's result.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from gridlayoutpdf import Block, Document

from ..assembly import document_bytes, join
from ..document import blank, paragraph, report
from ..styles import HEADING as HEADING_STYLE
from .frame_report import Manuscript, Unit, blocks as frame_blocks

LOAD_DIAGRAM = "load_diagram"  # FEMPython's (0610, 0620) or JRSNAP's (0710, 0720) load diagram
DATA_CHECK = "data_check"  # JRSNAP's データ確認図 (0710, 0720)
DIAGRAMS = "diagrams.heading"  # the key, after the stage prefix, of the load diagram heading


@dataclass(frozen=True)
class Insertion:
    """Where the pages named *name* go: after the unit *key*, or before it."""

    name: str
    key: str
    before: bool = False
    optional: bool = False  # the report may have no such pages (0611: a check Capacita skipped for zero forces)


def diagrams_heading(m: Manuscript, title: str) -> None:
    """The load diagram heading (8.3, 9.3, 10.3, 11.3), after which the load diagram pages go."""
    m.heading(DIAGRAMS, title, 1)


def _parts(units: Sequence[Unit], insertions: Sequence[Insertion]) -> list[tuple[Unit, ...]]:
    """*units* split at each insertion, in order: one more part than insertions (the last may be empty)."""
    keys = [unit.key for unit in units]
    if len(set(keys)) != len(keys):
        raise ValueError("帳票の単位に重複したキーがあります")
    if len({insertion.name for insertion in insertions}) != len(insertions):
        raise ValueError("差し込むページの名前が重複しています")
    cuts = []
    for insertion in insertions:
        if insertion.key not in keys:
            raise ValueError(f"差し込む位置の単位 {insertion.key} がありません")
        cuts.append(keys.index(insertion.key) + (0 if insertion.before else 1))
    if any(cut <= previous for previous, cut in zip([0, *cuts], cuts)):
        raise ValueError("差し込む位置が原稿の順になっていません")
    bounds = [0, *cuts, len(units)]
    return [tuple(units[start:end]) for start, end in zip(bounds, bounds[1:])]


def _document(units: Sequence[Unit], blocks: Callable[[Sequence[Unit]], list[Block]]) -> Document:
    if units[-1].kind != "heading":
        return report(*blocks(units))
    title = units[-1]
    found = blocks(units[:-1])
    blank(found)
    found.append(paragraph(title.value, left=title.left, style=HEADING_STYLE, block_id=title.key,
                           min_first=1, min_last=1))
    return report(*found)


def documents(units: Sequence[Unit], insertions: Sequence[Insertion], *,
              blocks: Callable[[Sequence[Unit]], list[Block]] = frame_blocks) -> tuple[Document, ...]:
    """The documents the report is laid out in, without the pages: one before each insertion and one after the last
    (none when the last insertion ends the manuscript)."""
    return tuple(_document(part, blocks) for part in _parts(units, insertions) if part)


def render_with_pages(units: Sequence[Unit], insertions: Sequence[Insertion], pages: Mapping[str, bytes],
                      path: str | Path, *,
                      blocks: Callable[[Sequence[Unit]], list[Block]] = frame_blocks) -> Path:
    """The report of *units* with the *pages* of each insertion where it says; atomically replaces *path*.

    WebPier's documents are the same bytes for the same input; the inserted pages are the other program's.
    """
    if unknown := sorted(set(pages) - {insertion.name for insertion in insertions}):
        raise ValueError(f"差し込む場所のないページがあります: {'・'.join(unknown)}")
    pieces: list[bytes] = []
    for part, insertion in zip(_parts(units, insertions), [*insertions, None]):
        if part:
            pieces.append(document_bytes(_document(part, blocks)))
        if insertion is None:
            continue
        if insertion.name in pages:
            pieces.append(pages[insertion.name])
        elif not insertion.optional:
            raise ValueError(f"差し込むページ {insertion.name} がありません")
    return join(pieces, path)
