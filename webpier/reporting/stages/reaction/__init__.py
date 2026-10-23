"""0600 上部工反力・橋脚自重: the report of the ReactionResult, authored as native GridLayoutPdf blocks.

Every number is a Printed value of the ReactionResult (or of the input it
echoes), written at its digits by reporting.numbers, in formula lines that
recompute from the printed numbers (ADR-0003). The wording and the layout are
this package's; nothing is calculated here.
"""

from __future__ import annotations

from pathlib import Path

from gridlayoutpdf import Document

from ....calc.reaction import ReactionResult
from ....inputs import PierInput
from . import buoyancy, dead, longitudinal, train, transverse, weight_parts
from .layout import document
from .manuscript import PREFIX, Manuscript, Unit, plain


def content(result: ReactionResult, pier: PierInput) -> tuple[Unit, ...]:
    """One ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript()
    dead.section(m, result)
    buoyancy.section(m, result.self_weight, pier, weight_parts.section(m, result.self_weight, pier))
    train.section(m, result, pier)
    longitudinal.section(m, result, pier)
    transverse.section(m, result, pier)
    return tuple(m.units)


def semantic_records(result: ReactionResult, pier: PierInput) -> list[dict[str, str]]:
    return [{"id": unit.identifier, "text": plain(unit.value)} for unit in content(result, pier)]


def build_reaction(result: ReactionResult, pier: PierInput) -> Document:
    """The 0600 report as a GridLayoutPdf Document (lay out or render it)."""
    return document(content(result, pier))


def render_reaction(result: ReactionResult, pier: PierInput, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes."""
    return build_reaction(result, pier).render(path, invariant=True)


def grid_documents(result: ReactionResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_reaction(result, pier),)


__all__ = ["PREFIX", "build_reaction", "content", "grid_documents", "render_reaction", "semantic_records"]
