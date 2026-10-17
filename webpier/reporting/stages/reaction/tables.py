"""The 0600 tables as authored specs (TableSpec): cells, spans and the measured row heights."""

from __future__ import annotations

from collections.abc import Sequence

from gridlayoutpdf import MathNode, Row

from ....calc.reaction.self_weight import Aggregate, Body, Part, WeightRow
from ....core.printed import Printed
from .manuscript import CellSpec, TableSpec, cells, sub, sup

GIRDER_ROW = 14.88  # reaction.girder / reaction.impact (0600 p1, p13)
SUMMARY_ROW, SUMMARY_HEADER = 23.04, 28.56  # reaction.horizontal_summary (0600 p37)

PART_NAMES = {Part.PEDESTAL: "桁受け", Part.BEAM: "はり", Part.COLUMN: "柱", Part.FOOTING: "フーチング",
              Part.OVERBURDEN: "上載土"}


def header(*values: str | MathNode) -> tuple[CellSpec, ...]:
    return tuple(CellSpec(value, align="center") for value in values)


def _unit(base: str, exponent: str) -> MathNode:
    return sup(base, exponent)


def volume_table(body: Body, names: Sequence[str], *, heights: bool = True) -> TableSpec:
    """V, x and V·x of each row of a part, and their sums (volume tables of 0600 p4-p9)."""
    first = ["", "V", sub("x", "L"), Row("V・", sub("x", "L"), gap=0), sub("x", "C"), Row("V・", sub("x", "C"), gap=0)]
    units = ["", _unit("m", "3"), "m", _unit("m", "4"), "m", _unit("m", "4")]
    if heights:
        first += ["y", "V・y"]
        units += ["m", _unit("m", "4")]
    rows = [header(*first), header(*units)]
    for name, row in zip(names, body.rows, strict=True):
        values: list[Printed | None] = [row.volume, row.x_l, row.moment_l, row.x_c, row.moment_c]
        if heights:
            values += [row.y, row.moment_y]
        rows.append(cells(name, *values, align="center"))
    total: list[Printed | None] = [body.volume, None, body.moment_l, None, body.moment_c]
    if heights:
        total += [None, body.moment_y]
    rows.append(cells("合計", *total, align="center"))
    count = len(first)
    widths = (72.6, *([58.08] * (count - 1)))
    return TableSpec(widths, tuple(rows), header_rows=2, row_height=GIRDER_ROW,
                     numeric_columns=tuple(range(1, count)))


def aggregate_table(total: Aggregate, shown: Sequence[WeightRow]) -> TableSpec:
    """N, x and N·x of the *shown* parts about a reference point, and the totals (0600 p10)."""
    first = ["", "N", sub("x", "L"), Row("N・", sub("x", "L"), gap=0), sub("x", "C"), Row("N・", sub("x", "C"), gap=0),
             "y", "N・y"]
    units = ["", "kN", "m", "kN・m", "m", "kN・m", "m", "kN・m"]
    rows = [header(*first), header(*units)]
    for row in shown:
        rows.append(cells(PART_NAMES[row.part], row.weight, row.x_l, row.moment_l, row.x_c, row.moment_c,
                          row.y, row.moment_y, align="center"))
    rows.append(cells("合計", total.weight, None, total.moment_l, None, total.moment_c, None, total.moment_y,
                      align="center"))
    return TableSpec((72.6, 58.08, 50.88, 63.36, 50.88, 63.36, 50.88, 63.36), tuple(rows), header_rows=2,
                     row_height=GIRDER_ROW, numeric_columns=tuple(range(1, 8)))


def summary(widths: Sequence[float], head: Sequence[tuple[CellSpec, ...]],
            body: Sequence[tuple[CellSpec, ...]], numeric: Sequence[int]) -> TableSpec:
    return TableSpec(tuple(widths), (*head, *body), header_rows=len(head), row_height=SUMMARY_ROW,
                     header_height=SUMMARY_HEADER if len(head) == 1 else None, numeric_columns=tuple(numeric))
