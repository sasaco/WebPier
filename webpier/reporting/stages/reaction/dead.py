"""6.1 Dead and snow loads at the supports, the bearings on this pier and their train shares."""

from __future__ import annotations

from gridlayoutpdf import Row

from ....calc.reaction import ReactionResult
from ....calc.reaction.dead import GirderDead, SupportLoads
from .manuscript import (
    CHAPTER, ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, cells, expr, join, sub,
)
from .tables import GIRDER_ROW, header

LOADS = (("d1", "固定死荷重 D1", "D1"), ("d2", "付加死荷重 D2", "D2"), ("snow2", "雪荷重 2年確率", "S2"),
         ("snow10", "雪荷重 10年確率", "S10"), ("snow30", "雪荷重 30年確率", "S30"))


def _support_table(supports: tuple[SupportLoads, ...]) -> TableSpec:
    rows = [header("", sub("R", "A"), sub("R", "B"), sub("R", "C"), sub("R", "D"))]
    for field, label, _ in LOADS:
        rows.append(cells(CellSpec(label, align="center"), *(getattr(support, field) for support in supports)))
    return TableSpec((116.16, 72.6, 72.6, 72.6, 72.6), tuple(rows), header_rows=1, row_height=GIRDER_ROW,
                     numeric_columns=(1, 2, 3, 4))


def bearing_name(slot: int) -> str:
    return f"G{slot + 1}"


def _bearing_table(girder: GirderDead) -> TableSpec:
    rows = [header("支承", "位置", "D1", "D2", "S2", "S10", "S30", "下り L1", "上り L2"),
            header("", "(m)", "(kN)", "(kN)", "(kN)", "(kN)", "(kN)", "", "")]
    for item in girder.bearings:
        bearing = item.bearing
        rows.append(cells(CellSpec(bearing_name(item.slot), align="center"), bearing.position, bearing.d1,
                          bearing.d2, bearing.snow2, bearing.snow10, bearing.snow30, bearing.shares.l1,
                          bearing.shares.l2))
    return TableSpec((43.56, 50.88, 58.08, 50.88, 50.88, 50.88, 50.88, 50.88, 50.88), tuple(rows), header_rows=2,
                     row_height=GIRDER_ROW, numeric_columns=tuple(range(1, 9)))


def _girder(m: Manuscript, key: str, title: str, support: str, girder: GirderDead) -> None:
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
    m.start(f"dead.{key}.shares")
    for index, item in enumerate(girder.bearings):
        shares = item.bearing.shares
        m.equation(f"dead.{key}.double.{item.slot}", bearing_name(item.slot), expr(shares.l1, "+", shares.l2),
                   item.double, gap=index == 0)
    doubles = [item.double for item in girder.bearings]
    if doubles:
        m.equation(f"dead.{key}.tracks", "n", expr(*join(doubles)), girder.track_total)
    else:
        m.value(f"dead.{key}.tracks", "n", girder.track_total, gap=True)
    m.end()


def section(m: Manuscript, result: ReactionResult) -> None:
    dead = result.dead
    m.heading("title", "§6. 上部工反力 及び 橋脚自重", CHAPTER)
    m.heading("dead.heading", "6.1 死荷重および雪荷重", SECTION)
    m.heading("dead.supports.heading", "(1) 支点反力", SUBSECTION)
    m.table("dead.supports.table", _support_table((dead.origin.far, dead.origin.pier, dead.end.pier, dead.end.far)),
            SUBSECTION)
    m.heading("dead.bearings.heading", "(2) 本橋脚の支承の荷重と列車の分担率", SUBSECTION)
    _girder(m, "origin", "1) 起点側桁（B支点）", "B", dead.origin)
    _girder(m, "end", "2) 終点側桁（C支点）", "C", dead.end)
