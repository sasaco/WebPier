"""The 0600 tables as authored specs (TableSpec): cells, spans and their widths in grid columns."""

from __future__ import annotations

from collections.abc import Sequence

from gridlayoutpdf import MathNode

from ....calc.reaction.self_weight import Part
from .manuscript import CellSpec, TableSpec

PART_NAMES = {Part.PEDESTAL: "桁受け", Part.BEAM: "はり", Part.COLUMN: "柱", Part.FOOTING: "フーチング",
              Part.OVERBURDEN: "上載土"}


def header(*values: str | MathNode) -> tuple[CellSpec, ...]:
    return tuple(CellSpec(value, align="center") for value in values)


def summary(widths: Sequence[int], head: Sequence[tuple[CellSpec, ...]],
            body: Sequence[tuple[CellSpec, ...]], numeric: Sequence[int]) -> TableSpec:
    return TableSpec(tuple(widths), (*head, *body), header_rows=len(head), numeric_columns=tuple(numeric))
