"""Tables on the common grid: column widths in grid columns, row heights in grid rows, rules as border styles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral

from gridlayoutpdf import (
    BorderStyle, Block, Cell, CellLines, GridSpec, Insets, LayoutContext, MathNode, MeasuredBlock, Paragraph,
    QuarterTurn, Table, TableBorders, TextStyle, measure_block,
)

from .styles import BODY, PITCH_X, PITCH_Y, count

# Inner clearance of a cell's text from its boundary (the rule's centre): the 2.4 pt Excel keeps on each side of a
# cell's text (gridlayoutpdf.equations.EXCEL_CELL_PADDING_PT) plus room for a medium rule's half width.
CELL_PADDING = Insets(0, 3.0, 0, 3.0)
# The reference's outer .96 pt and inner .12 pt rules become medium and hair (GridLayoutPdf FR-022).
OUTER, INNER = BorderStyle.MEDIUM, BorderStyle.HAIR


def cell(content: str | Block, *, colspan: int = 1, rowspan: int = 1,
         align: str | None = None, style: TextStyle = BODY, padding: Insets = CELL_PADDING) -> Cell:
    """A cell of text lines ("\\n" separated), one grid row per line."""
    if isinstance(content, str):
        content = CellLines(tuple(content.split("\n")), style=style, line_advance=PITCH_Y,
                            inner_padding=padding, align=align or "left")
    return Cell(content, colspan=colspan, rowspan=rowspan, align=align, padding=0)


def math_cell(content: MathNode, *, colspan: int = 1, rowspan: int = 1,
              align: str | None = None, style: TextStyle = BODY, padding: Insets = CELL_PADDING) -> Cell:
    """Keep MathNode.measure and Block.measure protocols unambiguous."""
    lines = CellLines((content,), style=style, line_advance=PITCH_Y, inner_padding=padding, align=align or "left")
    return Cell(lines, colspan=colspan, rowspan=rowspan, align=align, padding=0)


def table(widths: Sequence[int], rows: Sequence[Sequence[Cell | str]], *,
          row_heights: int | Sequence[int] | None = 1, header_rows: int = 0,
          numeric_columns: Sequence[int] = (), horizontal: Mapping[int, BorderStyle | None] | None = None,
          vertical: Mapping[int, BorderStyle | None] | None = None, inner: BorderStyle | None = INNER,
          outer: BorderStyle | None = OUTER, split: bool = True, block_id: str = "") -> Table:
    """A table of *widths* grid columns and *row_heights* grid rows, framed medium with hair rules inside.

    *horizontal* / *vertical* override the rule at a boundary (0 is the top / left edge; None draws no rule);
    *inner* / *outer* None draw no rules inside / no frame (an open table).
    """
    authored = tuple(tuple(value if isinstance(value, Cell) else cell(value) for value in row) for row in rows)
    heights = None
    if row_heights is not None:
        source = [row_heights] * len(authored) if isinstance(row_heights, Integral) else row_heights
        heights = tuple(count(value, "row height", minimum=1) for value in source)
    borders = TableBorders(inner, outer=outer, horizontal=dict(horizontal or {}), vertical=dict(vertical or {}))
    return Table(tuple(count(width, "column width", minimum=1) for width in widths), authored, row_heights=heights,
                 header_rows=header_rows, numeric_columns=tuple(numeric_columns), split=split, borders=borders,
                 block_id=block_id)


@dataclass(frozen=True)
class VerticalLabel:
    """Text turned counterclockwise in one grid column, *length* grid rows long, for a tall merged cell.

    The text is laid out on a local grid with the page's pitches swapped (GridLayoutPdf QuarterTurn), so that the grid
    Excel writes it as a cell whose text runs at 90 degrees.
    """

    text: str
    length: int
    style: TextStyle = BODY
    block_id: str = ""

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        turned = QuarterTurn(Paragraph(self.text, style=self.style, align="center", block_id=self.block_id + ".text"),
                             turns=1, local_grid=GridSpec(0, 0, PITCH_Y, PITCH_X, count(self.length, "length", minimum=1),
                                                          max(1, int(available_width / PITCH_X + 1e-9))),
                             block_id=self.block_id)
        return measure_block(turned, context, available_width)
