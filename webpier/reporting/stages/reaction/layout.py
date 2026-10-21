"""Lay the 0600 manuscript out as native GridLayoutPdf blocks on the common grid; pages break by content.

Every position is a body column and every height a whole number of grid rows (styles), so that the pages map onto the
grid Excel cell by cell.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from gridlayoutpdf import (Block, BorderStyle, BreakHint, Cell, CellLines, Document, Equation, GridSpec, KeepWithNext,
                           LayoutContext, LayoutOverflowError, Leading, MeasuredBlock, Operator, Paragraph,
                           PreferKeepTogether, QuarterTurn, Row, SideRule, TermStop, measure_block)

from ...document import blank, columns, heading, indent_to, math_line, paragraph, report, spacer
from ...equations import definitions, equation_group
from ...styles import BODY, BODY_COLUMNS, PITCH_X, PITCH_Y, columns_pt
from ...tables import CELL_PADDING, table
from .figures import LoadingFigure, OutlineFigure
from .manuscript import (
    RESULT_EQUAL, RESULT_RIGHT, RULE_X, UNIT_START, CellSpec, Pair, TableSpec, Unit,
)

FIGURES = {"outline": OutlineFigure, "loading": LoadingFigure}
RULE_STYLE = BorderStyle.MEDIUM  # the reference's 0.72 pt bracket (0600 p16)


def _lines(spec: CellSpec) -> int:
    return spec.content.count("\n") + 1 if isinstance(spec.content, str) else 1


def _cell(spec: CellSpec, advance: float) -> Cell:
    """A cell of text lines ("\\n" separated) or one math line, one grid row (*advance* pt) per line."""
    lines = tuple(spec.content.split("\n")) if isinstance(spec.content, str) else (spec.content,)
    content = CellLines(lines, style=BODY, line_advance=advance, inner_padding=CELL_PADDING, align=spec.align or "left")
    return Cell(content, colspan=spec.colspan, rowspan=spec.rowspan, align=spec.align, padding=0)


def _heights(spec: TableSpec) -> list[int]:
    """Grid rows of each table row: a row per line of its tallest cell; a spanning cell's extra lines go to the
    last row it spans."""
    heights = [1] * len(spec.rows)
    spans: list[tuple[int, int, int]] = []  # (first row, rows, lines)
    occupied: dict[tuple[int, int], bool] = {}
    for index, row in enumerate(spec.rows):
        column = 0
        for item in row:
            while occupied.get((index, column)):
                column += 1
            for down in range(item.rowspan):
                for across in range(item.colspan):
                    occupied[(index + down, column + across)] = True
            column += item.colspan
            if item.rowspan == 1:
                heights[index] = max(heights[index], _lines(item))
            else:
                spans.append((index, item.rowspan, _lines(item)))
    for first, count, lines in spans:
        missing = lines - sum(heights[first:first + count])
        if missing > 0:
            heights[first + count - 1] += missing
    return heights


def _raw_table(spec: TableSpec, block_id: str, advance: float = PITCH_Y) -> Block:
    rows = [[_cell(item, advance) for item in row] for row in spec.rows]
    return table(spec.widths, rows, row_heights=_heights(spec), header_rows=spec.header_rows,
                 numeric_columns=spec.numeric_columns, block_id=block_id)


def _table(spec: TableSpec, block_id: str) -> Block:
    return PreferKeepTogether(_raw_table(spec, block_id))


def _rotated(spec: TableSpec, block_id: str) -> Block:
    """The table laid out on a local grid with the page's pitches swapped, then turned counterclockwise (GridLayoutPdf
    QuarterTurn): one indivisible part whose height on the page is the table's width, written to the grid Excel as
    cells whose text runs at 90 degrees."""
    local = GridSpec(0, 0, PITCH_Y, PITCH_X, sum(spec.widths), sum(_heights(spec)))
    return QuarterTurn(_raw_table(spec, block_id + ".table", PITCH_X), turns=1, local_grid=local, block_id=block_id)


def _pair(pair: Pair, left: int, second: int, block_id: str) -> Block:
    """Two texts, the second from its own column (0600 p16 "・0.8 LR  [… の組合せ]"), a grid row per line."""
    first = Leading(Paragraph(pair.first, style=BODY, block_id=block_id + ".first"), 1)
    rest = Leading(Paragraph(pair.second, style=BODY, block_id=block_id + ".second"), 1)
    return indent_to(columns(first, rest, widths=(second - left, BODY_COLUMNS - second), gap=0, block_id=block_id),
                     left)


def _anchors(unit: Unit) -> tuple[int, int | None, bool, bool]:
    """The columns of an equation: its left edge, its "=" and whether it has a result and a unit."""
    result = unit.value.result is not None
    return unit.left, unit.first_equal, result, result and unit.value.unit is not None


def _joins(unit: Unit, following: Unit) -> bool:
    """*following* continues the equations of *unit*: same columns, group and rule, no blank line between."""
    return (unit.kind == following.kind == "equation" and not following.gap_before
            and following.group == unit.group and following.ruled == unit.ruled
            and _anchors(unit) == _anchors(following))


_BREAKS = (frozenset(("=", "+", "−", "-")), frozenset(("×", "/")))  # where a long line breaks, by preference


def _pairs(rhs: object) -> list[tuple[TermStop, object]] | None:
    """The (stop, term) pairs of a term-column RHS (its break hints dropped), or None for another RHS."""
    if not isinstance(rhs, Row) or not rhs.items or not isinstance(rhs.items[0], TermStop):
        return None
    items = [item for item in rhs.items if not isinstance(item, BreakHint)]
    return list(zip(items[::2], items[1::2]))


def _row(pairs: Sequence[tuple[TermStop, object]], gap: float) -> Row:
    return Row(*(item for pair in pairs for item in pair), gap=gap)


@dataclass(frozen=True)
class _Equations:
    """Equations sharing their columns, a grid row per display line (equations.equation_group).

    A term-column equation too long for one line (its terms in whole grid columns from its "=" to the body's right
    edge) is written on several: each further line takes the operator it begins with in the "=" column and its terms
    from the "=" column on (0600 p16 "Rm = … + 1.23 × … / + 400.00 = 2851.84 kN"), and the result stands on the last.
    The lines break before "=", "+" or "−" where they can, else before "×" or "/"; the text and its order do not change.
    """

    equations: tuple[Equation, ...]
    keep: tuple[bool, ...]
    left: int
    first_equal: int
    result: bool
    unit: bool
    block_id: str

    def _group(self, equations: Sequence[Equation], keep: Sequence[bool]) -> Block:
        return equation_group(*equations, left=self.left, first_equal=self.first_equal,
                              second_equal=RESULT_EQUAL if self.result else None,
                              result_right=RESULT_RIGHT if self.result else None,
                              unit_start=UNIT_START if self.unit else None, block_id=self.block_id, keep=tuple(keep))

    def _count(self, equations: Sequence[Equation], context: LayoutContext, width: float) -> int | None:
        """The display lines of *equations* laid out together, or None when they do not fit."""
        if not equations:
            return 0
        try:
            measured = measure_block(self._group(equations, [False] * len(equations)), context, width)
        except LayoutOverflowError:
            return None
        return sum(part.rows for part in measured.parts)  # a grid row per display line

    def _lines(self, before: list[Equation], equation: Equation, context: LayoutContext,
               width: float) -> list[Equation]:
        """*equation* on as many lines as it needs after the lines *before* it in the group (with which lines of the
        same shape share their term columns)."""
        base = self._count(before, context, width)

        def fits(lines: list[Equation], line: Equation) -> bool:
            found = self._count([*before, *lines, line], context, width)
            return base is not None and found is not None and found == base + len(lines) + 1

        pairs = _pairs(equation.rhs)
        if pairs is None or fits([], equation):
            return [equation]
        gap = equation.rhs.gap
        lines: list[Equation] = []
        head = replace(equation, rhs=_row(pairs, gap), result=None, unit=None)  # the first line keeps lhs and label
        while True:
            last = replace(head, rhs=_row(pairs, gap), result=equation.result, unit=equation.unit,
                           result_relation=equation.result_relation)
            if fits(lines, last):
                return [*lines, last]
            cut = next((index for breaks in _BREAKS for index in range(len(pairs) - 1, 0, -1)
                        if isinstance(pairs[index][1], Operator) and pairs[index][1].text in breaks
                        and fits(lines, replace(head, rhs=_row(pairs[:index], gap)))), None)
            if cut is None:
                return [*lines, last]  # nothing shorter fits: equation_group reports the line
            lines.append(replace(head, rhs=_row(pairs[:cut], gap)))
            operator = pairs[cut][1]
            pairs = pairs[cut + 1:]
            head = Equation("", _row(pairs, gap), relation=operator.text, style=equation.style,
                            block_id=equation.block_id)

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        try:
            return measure_block(self._group(self.equations, self.keep), context, available_width)
        except LayoutOverflowError:
            pass  # a line too long for its columns: wrap it below
        equations: list[Equation] = []
        keep: list[bool] = []
        for equation, kept in zip(self.equations, self.keep, strict=True):
            lines = self._lines(equations, equation, context, available_width)
            equations += lines
            keep += [True] * (len(lines) - 1) + [kept]
        return measure_block(self._group(equations, keep), context, available_width)


def _equations(run: Sequence[Unit], keep: tuple[bool, ...]) -> Block:
    """Consecutive equations in one group, so that their term columns line up across the lines (0600 p16)."""
    left, first_equal, result, has_unit = _anchors(run[0])
    assert first_equal is not None
    return _Equations(tuple(unit.value for unit in run), keep, left, first_equal, result, has_unit,
                      run[0].identifier)


def _block(unit: Unit) -> Block:
    if unit.kind == "heading":
        return heading(unit.value, left=unit.left, block_id=unit.identifier)
    if unit.kind == "paragraph":
        return paragraph(unit.value, left=unit.left, block_id=unit.identifier)
    if unit.kind == "pair":
        assert unit.first_equal is not None
        return _pair(unit.value, unit.left, unit.first_equal, unit.identifier)
    if unit.kind == "definitions":
        assert unit.first_equal is not None
        return definitions(*unit.value, left=unit.left, colon=unit.first_equal, block_id=unit.identifier)
    if unit.kind == "table":
        return indent_to(_table(unit.value, unit.identifier), unit.left)
    if unit.kind == "rotated":
        return indent_to(_rotated(unit.value, unit.identifier), unit.left)
    if unit.kind == "figure":
        return indent_to(FIGURES[unit.value.kind](unit.value.data, unit.identifier), unit.left)
    return math_line(unit.value, left=unit.left, block_id=unit.identifier)


def _ruled(out: list[Block], ruled: list[bool]) -> list[Block]:
    """Each run of ruled blocks gets the rule on the boundary before body column RULE_X, over the whole rows of
    its blocks (0600 p16)."""
    x = columns_pt(RULE_X)
    return [SideRule(block, x, style=RULE_STYLE) if rule else block for block, rule in zip(out, ruled, strict=True)]


def blocks(units: Sequence[Unit]) -> list[Block]:
    """Blocks in manuscript order: a heading and a group's units stay with what follows them.

    A heading, table or figure has one blank line before and after it; blank lines never stack.
    A ruled unit and the blank lines next to it are bracketed by the rule.
    """
    def kept(index: int) -> bool:
        unit, following = units[index], units[index + 1] if index + 1 < len(units) else None
        return following is not None and (unit.kind == "heading" or unit.keep
                                          or bool(unit.group) and following.group == unit.group)

    out: list[Block] = []
    ruled: list[bool] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if unit.kind in ("heading", "table", "rotated", "figure") or unit.gap_before:
            before = len(out)
            blank(out)
            if len(out) > before and (unit.ruled or index > 0 and units[index - 1].ruled):
                # The rule makes the blank line visible: it continues the chain of a kept group.
                out[-1] = KeepWithNext(out[-1]) if kept(index - 1) else out[-1]
                ruled.append(True)
            else:
                ruled.extend([False] * (len(out) - before))
        end = index + 1
        if unit.kind == "equation":
            while end < len(units) and _joins(units[end - 1], units[end]):
                end += 1
            block = _equations(units[index:end], tuple(kept(position) for position in range(index, end)))
        else:
            block = _block(unit)
        out.append(KeepWithNext(block) if kept(end - 1) else block)
        ruled.append(unit.ruled)
        index = end
        if unit.kind == "heading":
            out.append(KeepWithNext(spacer()))
            ruled.append(False)
        elif unit.kind in ("table", "rotated", "figure"):
            out.append(spacer())
            ruled.append(False)
    return _ruled(out, ruled)


def document(units: Sequence[Unit]) -> Document:
    return report(*blocks(units))
