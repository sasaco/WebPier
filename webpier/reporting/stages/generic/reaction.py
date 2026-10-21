"""0600 with a load model (decision 70): the dead loads D1 and D2 at the supports and the pier self weight.

6.1 prints D1 and D2 only (the snow and the train shares are the load model's, and are not printed); 6.2 is the
self weight of the train path's report (reporting.stages.reaction weight_parts / weight_totals). The train, the
forces of the girders and the impact (the train path's 6.3 onward) are the load model's and are not part of it.
"""

from __future__ import annotations

from pathlib import Path

from gridlayoutpdf import Document, Row

from ....calc.reaction import DeadReactionResult
from ....calc.reaction.dead import GirderDeadLoads
from ....inputs import PierInput
from ..reaction import weight_parts, weight_totals
from ..reaction.dead import bearing_name
from ..reaction.layout import document
from ..reaction.manuscript import (
    CHAPTER, ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, Unit, cells, expr, join, plain, sub,
)
from ..reaction.tables import header

LOADS = (("d1", "固定死荷重 D1", "D1"), ("d2", "付加死荷重 D2", "D2"))


def _support_table(dead) -> TableSpec:
    supports = (dead.origin.far, dead.origin.pier, dead.end.pier, dead.end.far)
    rows = [header("", sub("R", "A"), sub("R", "B"), sub("R", "C"), sub("R", "D"))]
    for field, label, _ in LOADS:
        rows.append(cells(CellSpec(label, align="center"), *(getattr(support, field) for support in supports)))
    return TableSpec((8, 5, 5, 5, 5), tuple(rows), header_rows=1, numeric_columns=(1, 2, 3, 4))


def _bearing_table(girder: GirderDeadLoads) -> TableSpec:
    rows = [header("支承", "位置", "D1", "D2"), header("", "(m)", "(kN)", "(kN)")]
    for item in girder.bearings:
        bearing = item.bearing
        rows.append(cells(CellSpec(bearing_name(item.slot), align="center"), bearing.position, bearing.d1,
                          bearing.d2))
    return TableSpec((2, 3, 3, 3), tuple(rows), header_rows=2, numeric_columns=(1, 2, 3))


def _girder(m: Manuscript, key: str, title: str, support: str, girder: GirderDeadLoads) -> None:
    m.heading(f"dead.{key}.heading", title, ITEM)
    if girder.bearings:
        m.table(f"dead.{key}.bearings", _bearing_table(girder), SUBSECTION)
    m.start(f"dead.{key}.sums")
    for field, _, symbol in LOADS:
        total = getattr(girder.pier, field)
        values = [getattr(item.bearing, field) for item in girder.bearings]
        lhs = Row(sub("R", support), f"({symbol})", gap=0)
        if values:
            m.equation(f"dead.{key}.sum.{field}", lhs, expr(*join(values)), total, gap=field == "d1", medium=True)
        else:
            m.value(f"dead.{key}.sum.{field}", lhs, total, medium=True)
    m.end()


def content(result: DeadReactionResult, pier: PierInput) -> tuple[Unit, ...]:
    """One ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript()
    dead = result.dead
    m.heading("title", "§6. 上部工反力 及び 橋脚自重", CHAPTER)
    m.heading("dead.heading", "6.1 死荷重", SECTION)
    m.paragraph("dead.note", "死荷重以外の上部工の作用は荷重モデルによる（0610・0620・0710・0720 の各章）．", SUBSECTION)
    m.heading("dead.supports.heading", "(1) 支点反力", SUBSECTION)
    m.table("dead.supports.table", _support_table(dead), SUBSECTION)
    m.heading("dead.bearings.heading", "(2) 本橋脚の支承の荷重", SUBSECTION)
    _girder(m, "origin", "1) 起点側桁（B支点）", "B", dead.origin)
    _girder(m, "end", "2) 終点側桁（C支点）", "C", dead.end)
    weight_totals.section(m, result.self_weight, pier, weight_parts.section(m, result.self_weight, pier))
    return tuple(m.units)


def semantic_records(result: DeadReactionResult, pier: PierInput) -> list[dict[str, str]]:
    return [{"id": unit.identifier, "text": plain(unit.value)} for unit in content(result, pier)]


def build_dead_reaction(result: DeadReactionResult, pier: PierInput) -> Document:
    return document(content(result, pier))


def render_dead_reaction(result: DeadReactionResult, pier: PierInput, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes."""
    return build_dead_reaction(result, pier).render(path, invariant=True)


def grid_documents(result: DeadReactionResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_dead_reaction(result, pier),)
