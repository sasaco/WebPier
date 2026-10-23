"""6.2 (1)-(2) The pier shape, and the self weight of the parts as table 6.2.1 (decision 79).

Table 6.2.1 is written as the table 2.1.2 of the 設計計算例 (Example橋脚3 p.72):
each row of a part's volume is V as a product of printed lengths, with γ and
W = V × γ; a part of more rows has its weight W, the sum of the rows, after the
table. A row whose V is 0 is left out and the symbols V1, V2, … close up (as
桁受け, decision 41). The centroids are of the calculation only.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gridlayoutpdf import Row

from ....calc.reaction.self_weight import Body, HaunchShape, Part, SelfWeightResult, VolumeRow
from ....core.printed import Printed
from ....inputs import PierInput
from .figures import outline_figure
from .manuscript import SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, Wrapped, cells, expr, join, sub, sup
from .tables import PART_NAMES, header

TITLE = "橋脚く体，フーチングおよび上載土"
TABLE = "表 6.2.1"


def pedestal_shown(sw: SelfWeightResult) -> bool:
    """桁受け is printed only when its volume is not 0 (decision 41)."""
    return sw.pedestal.volume.value != 0


def _haunch(height: Printed, lower: tuple[Printed, Printed], upper: tuple[Printed, Printed]) -> tuple[Any, ...]:
    """h / 6 × (b0 × W + B × w0 + 2 × (B × W + b0 × w0)): the prismatoid between the lower and upper faces."""
    (b0, w0), (b, w) = lower, upper
    return (height, "/", 6, "×", "(", b0, "×", w, "+", b, "×", w0, "+", 2, "×", "(", b, "×", w, "+", b0, "×", w0,
            ")", ")")


def _parts(sw: SelfWeightResult, pier: PierInput) -> list[tuple[Part, Body, list[tuple[Any, ...]]]]:
    """Each part with its body and the numbers of V of each of its rows, in the order of the rows."""
    s = pier.substructure
    b, w, h = s.b, s.w, s.h
    bf, wf = sw.footing_length, sw.footing_width
    beam: HaunchShape = sw.beam_haunch_shape
    footing_haunch = _haunch(h[5], (bf, wf), (b[8], w[8]))
    parts = [
        (Part.PEDESTAL, sw.pedestal, [(b[3], "×", w[3], "×", h[1])]),
        (Part.BEAM, sw.beam, [(b[1], "×", w[1], "×", h[2]),
                              _haunch(h[3], (beam.lower_length, beam.lower_width), (b[1], w[1]))]),
        (Part.COLUMN, sw.column, [(b[6], "×", w[6], "×", h[4])]),
        (Part.FOOTING, sw.footing, [footing_haunch, (bf, "×", wf, "×", h[6])]),
        (Part.OVERBURDEN, sw.overburden, [(bf, "×", wf, "×", "(", s.df1, "+", s.df2, ")", "/", 2),
                                          ("−", b[6], "×", w[6], "×", sw.soil_depth_at_column),
                                          (bf, "×", wf, "×", h[5]),
                                          ("−", *footing_haunch)]),
    ]
    return [part for part in parts if part[0] is not Part.PEDESTAL or pedestal_shown(sw)]


def shown_rows(body: Body) -> list[tuple[VolumeRow, Printed]]:
    """The printed rows of a part and their weights W: those whose V is not 0."""
    assert body.weights is not None
    return [(row, weight) for row, weight in zip(body.rows, body.weights, strict=True) if row.volume.value != 0]


def _table(parts: Sequence[tuple[Part, Body, list[tuple[Any, ...]]]]) -> TableSpec:
    """区分, the symbol, V as numbers = its value, γ and W (table 2.1.2 without the buoyancy columns)."""
    rows = [(CellSpec("", colspan=2, rowspan=3),
             CellSpec(Row("V (", sup("m", "3"), ")", gap=0), colspan=3, rowspan=3, align="center"),
             CellSpec("自重", colspan=2, align="center")),
            header("γ", "W"),
            header(Row("(kN/", sup("m", "3"), ")", gap=0), "(kN)")]
    symbol = 0
    for part, body, numbers in parts:
        assert body.weights is not None
        shown = [(row, weight, volume) for row, weight, volume in zip(body.rows, body.weights, numbers, strict=True)
                 if row.volume.value != 0]
        for index, (row, weight, volume) in enumerate(shown):
            symbol += 1
            name = (CellSpec(PART_NAMES[part], rowspan=len(shown), align="center"),) if index == 0 else ()
            rows.append((*name, CellSpec(sub("V", str(symbol)), align="center"),
                         CellSpec(Wrapped(expr(*volume, open_groups=True, nested=True))), CellSpec("=", align="center"),
                         *cells(row.volume, body.unit_weight, weight)))
    # 区分 and the symbol, V as numbers, "=" and its value with no rules between them, then γ and W.
    return TableSpec((4, 2, 12, 1, 3, 3, 3), tuple(rows), header_rows=3, numeric_columns=(4, 5, 6),
                     open_boundaries=(3, 4))


def section(m: Manuscript, sw: SelfWeightResult, pier: PierInput) -> int:
    """(1) the shape and (2) table 6.2.1 with the weights of the parts of more rows; returns the next item number."""
    m.heading("weight.heading", "6.2 橋脚自重", SECTION)
    m.heading("weight.shape.heading", "(1) 橋脚の形状", SUBSECTION)
    m.figure("weight.shape.figure", outline_figure(pier, sw), SECTION)
    parts = _parts(sw, pier)
    m.heading("weight.parts.heading", f"(2) {TITLE}", SUBSECTION)
    m.paragraph("weight.parts.text", f"{TITLE}の自重を{TABLE} に示す．")
    m.caption("weight.parts.title", f"{TABLE} {TITLE}の自重", SUBSECTION)
    m.table("weight.parts.table", _table(parts), SUBSECTION)
    for part, body, _ in parts:
        weights = [weight for _, weight in shown_rows(body)]
        if len(weights) > 1:
            m.start(f"weight.{part.value}.sum")
            m.paragraph(f"weight.{part.value}.sum.label", PART_NAMES[part], gap=True)
            m.formula(f"weight.{part.value}.sum.weight", "W", None, join(weights), body.weight)
            m.end()
    return 3
