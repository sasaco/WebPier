"""Measured point widths and heights around the public native table API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from numbers import Real

from gridlayoutpdf import (
    Block, Cell, CellLines, Insets, LayoutContext, LayoutPart, MathNode, MeasuredBlock,
    Table, Text, TextStyle, command_bounds,
)

from .styles import BODY, SMALL, grid_units


def cell(content: str | Block, *, colspan: int = 1, rowspan: int = 1,
         align: str | None = None, style: TextStyle = BODY,
         line_advance: float = 12.84) -> Cell:
    """Use internal clearance before one rounding, never the default outer 3 pt."""
    if isinstance(content, str):
        content = CellLines(tuple(content.split("\n")), style=style, line_advance=line_advance,
                            inner_padding=Insets(1.08, 1.08, 1.08, 1.08), align=align or "left")
    return Cell(content, colspan=colspan, rowspan=rowspan, align=align, padding=0)


def math_cell(content: MathNode, *, colspan: int = 1, rowspan: int = 1,
              align: str | None = None, style: TextStyle = BODY) -> Cell:
    """Keep MathNode.measure and Block.measure protocols unambiguous."""
    lines = CellLines((content,), style=style, inner_padding=Insets(1.08, 1.08, 1.08, 1.08))
    return Cell(lines, colspan=colspan, rowspan=rowspan, align=align, padding=0)


def table(widths: Sequence[float], rows: Sequence[Sequence[Cell | str]], *,
          row_heights: float | Sequence[float] | None = 14.28, header_rows: int = 0,
          numeric_columns: Sequence[int] = (), horizontal_rules: Sequence[float] | None = None,
          vertical_rules: Sequence[float] | None = None, split: bool = True,
          block_id: str = "") -> Table:
    authored = tuple(tuple(value if isinstance(value, Cell) else cell(value) for value in row) for row in rows)
    heights = None
    if row_heights is not None:
        source = [row_heights] * len(authored) if isinstance(row_heights, Real) else row_heights
        heights = tuple(grid_units(value) for value in source)
    horizontal = (tuple(horizontal_rules) if horizontal_rules is not None else
                  (.96, *([.12] * max(0, len(authored) - 1)), .96))
    vertical = (tuple(vertical_rules) if vertical_rules is not None else
                (.96, *([.12] * max(0, len(widths) - 1)), .96))
    return Table(tuple(grid_units(width) for width in widths), authored, row_heights=heights,
                 header_rows=header_rows, numeric_columns=tuple(numeric_columns), split=split,
                 horizontal_rules=horizontal, vertical_rules=vertical, block_id=block_id)


@dataclass(frozen=True)
class VerticalLabel:
    """Native rotated text with conservative bounds, for tall merged cells."""

    text: str
    style: TextStyle = SMALL
    block_id: str = ""

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        command = Text(0, 0, self.text, self.style, quarter_turns=1)
        bounds = command_bounds(command, context.fonts)
        command = replace(command, x=1.08 - bounds.x, y=1.08 - bounds.y)
        rows = context.rows_for(bounds.height + 2.16)
        return MeasuredBlock(bounds.width + 2.16, context.profile.grid.pitch_y,
                             (LayoutPart(rows, (command,)),), keep_together=True, block_id=self.block_id)
